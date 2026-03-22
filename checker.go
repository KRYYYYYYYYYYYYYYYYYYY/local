package main

import "C"
import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/xtls/xray-core/core"
	"github.com/xtls/xray-core/infra/conf/serial"

	_ "github.com/xtls/xray-core/main/distro/all"
)

var probeTargets = []string{
	"https://www.gstatic.com/generate_204",
	"https://cp.cloudflare.com/generate_204",
	"https://connectivitycheck.gstatic.com/generate_204",
}

func pickFreeLocalPort() (int, error) {
	l, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return 0, err
	}
	defer l.Close()
	return l.Addr().(*net.TCPAddr).Port, nil
}

func buildConfigJSON(socksPort int, addr string, port int, uuid, flow, sni, pbk, sid string) ([]byte, error) {
	cfg := map[string]any{
		"log": map[string]any{
			"loglevel": "none",
		},
		"inbounds": []map[string]any{
			{
				"port":     socksPort,
				"listen":   "127.0.0.1",
				"protocol": "socks",
				"settings": map[string]any{"auth": "noauth", "udp": true},
			},
		},
		"outbounds": []map[string]any{
			{
				"protocol": "vless",
				"settings": map[string]any{
					"vnext": []map[string]any{
						{
							"address": addr,
							"port":    port,
							"users": []map[string]any{
								{"id": uuid, "encryption": "none", "flow": flow},
							},
						},
					},
				},
				"streamSettings": map[string]any{
					"network":  "tcp",
					"security": "reality",
					"realitySettings": map[string]any{
						"show":        false,
						"fingerprint": "chrome",
						"serverName":  sni,
						"publicKey":   pbk,
						"shortId":     sid,
						"spiderX":     "/",
					},
				},
			},
		},
	}
	return json.Marshal(cfg)
}

func probeViaSocks(client *http.Client, target string, timeoutSec int) int {
	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(timeoutSec)*time.Second)
	defer cancel()

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, target, nil)
	if err != nil {
		return 0
	}
	req.Header.Set("User-Agent", "Mozilla/5.0")
	start := time.Now()
	resp, err := client.Do(req)
	if err != nil {
		return 0
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusNoContent || resp.StatusCode == http.StatusOK {
		return int(time.Since(start).Milliseconds())
	}
	return 0
}

//export CheckVlessL7
func CheckVlessL7(cAddr *C.char, cPort int, cUuid *C.char, cSni *C.char, cPbk *C.char, cSid *C.char, cFlow *C.char, timeout int) int {
	addr := strings.TrimSpace(C.GoString(cAddr))
	uuid := strings.TrimSpace(C.GoString(cUuid))
	sni := strings.TrimSpace(C.GoString(cSni))
	pbk := strings.TrimSpace(C.GoString(cPbk))
	sid := strings.TrimSpace(C.GoString(cSid))
	flow := strings.TrimSpace(C.GoString(cFlow))
	if addr == "" || uuid == "" || sni == "" || pbk == "" || cPort <= 0 {
		return 0
	}
	if timeout <= 0 {
		timeout = 5
	}

	// 1. БЫСТРЫЙ TCP ПРОБ (из crazy_xray_checker)
	// Если порт закрыт, выходим за 500мс, не запуская Xray
	d := net.Dialer{Timeout: 500 * time.Millisecond}
	conn, err := d.Dial("tcp", net.JoinHostPort(addr, fmt.Sprint(cPort)))
	if err != nil {
		return 0
	}
	conn.Close()

	socksPort, err := pickFreeLocalPort()
	if err != nil {
		return 0
	}

		// 2. ГЕНЕРАЦИЯ КОНФИГА (без ручной строковой сборки)
	configJSON, err := buildConfigJSON(socksPort, addr, cPort, uuid, flow, sni, pbk, sid)
	if err != nil || !json.Valid(configJSON) {
		return 0
	}

	rawConfig, err := serial.DecodeJSONConfig(bytes.NewReader(configJSON))
	if err != nil {
		return 0
	}

	serverConfig, err := rawConfig.Build()
	if err != nil {
		return 0
	}

	instance, err := core.New(serverConfig)
	if err != nil {
		return 0
	}

	if err := instance.Start(); err != nil {
		return 0
	}
	defer instance.Close()

	// Уменьшили паузу до 150мс (этого достаточно после TCP проба)
	time.Sleep(150 * time.Millisecond)

	// 3. ПРОВЕРКА С ЗАМЕРОМ ВРЕМЕНИ
	proxyURL, err := url.Parse(fmt.Sprintf("socks5://127.0.0.1:%d", socksPort))
	if err != nil {
		return 0
	}
	transport := &http.Transport{
		Proxy:                 http.ProxyURL(proxyURL),
		DisableKeepAlives:     true,
		IdleConnTimeout:       1 * time.Second,
		TLSHandshakeTimeout:   time.Duration(timeout) * time.Second,
		ResponseHeaderTimeout: time.Duration(timeout) * time.Second,
	}
	defer transport.CloseIdleConnections()
	client := &http.Client{
		Transport: transport,
		Timeout:   time.Duration(timeout) * time.Second,
	}
	
	for _, target := range probeTargets {
		latency := probeViaSocks(client, target, timeout)
		if latency > 0 {
			return latency
		}
	}

	return 0
}

func main() {}
