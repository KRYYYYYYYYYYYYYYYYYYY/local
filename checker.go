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
	"os"
	"regexp"
	"strings"
	"time"

	"github.com/xtls/xray-core/core"
	"github.com/xtls/xray-core/infra/conf/serial"

	_ "github.com/xtls/xray-core/main/distro/all"
)

var probeTargets = []string{
	"https://www.gstatic.com/generate_204",
	"https://www.google.com/generate_204",
	"https://cp.cloudflare.com/generate_204",
	"https://connectivitycheck.gstatic.com/generate_204",
	"https://clients3.google.com/generate_204",
	"https://raw.githubusercontent.com/",
	"https://cdn.jsdelivr.net/",
	"https://pastebin.com/",
}

var appLikeTargets = map[string]bool{
	"https://raw.githubusercontent.com/": true,
	"https://cdn.jsdelivr.net/":          true,
	"https://pastebin.com/":              true,
}

var probeUserAgents = []string{
	"Mozilla/5.0 (Linux; Android 13; SM-A336B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
	"Mozilla/5.0 (Linux; Android 16; SM-A336B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.7680.119 Mobile Safari/537.36",
	"Mozilla/5.0 (Linux; Android 13; SM-A336B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6367.179 Mobile Safari/537.36 happ/3.15.1",
	"Happ/3.15.1",
	"okhttp/4.12.0 v2rayNG/1.12.28",
}

var uuidRegex = regexp.MustCompile(`(?i)^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`)

func activeProbeTargets() []string {
	fast := strings.EqualFold(strings.TrimSpace(os.Getenv("CHECKER_CI_FAST")), "1") ||
		strings.EqualFold(strings.TrimSpace(os.Getenv("CHECKER_CI_FAST")), "true")
	if fast {
		return probeTargets[:2]
	}
	return probeTargets
}

func shouldUseFastMode() bool {
	return strings.EqualFold(strings.TrimSpace(os.Getenv("CHECKER_CI_FAST")), "1") ||
		strings.EqualFold(strings.TrimSpace(os.Getenv("CHECKER_CI_FAST")), "true")
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

func probeViaSocks(client *http.Client, target string, timeoutSec int, userAgent string) int {
	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(timeoutSec)*time.Second)
	defer cancel()

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, target, nil)
	if err != nil {
		return 0
	}
	if strings.TrimSpace(userAgent) != "" {
		req.Header.Set("User-Agent", userAgent)
	}
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

func probeTargetWithFallbackUA(client *http.Client, target string, timeoutSec int, seed int64) int {
	if len(probeUserAgents) == 0 {
		return probeViaSocks(client, target, timeoutSec, "")
	}
	primary := probeUserAgents[seed%int64(len(probeUserAgents))]
	if latency := probeViaSocks(client, target, timeoutSec, primary); latency > 0 {
		return latency
	}
	secondary := "okhttp/4.12.0 v2rayNG/1.12.28"
	if strings.EqualFold(primary, secondary) {
		return 0
	}
	return probeViaSocks(client, target, timeoutSec, secondary)
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
	if !uuidRegex.MatchString(uuid) {
		return 0
	}
	if timeout <= 0 {
		timeout = 5
	}

	// 1. БЫСТРЫЙ TCP ПРОБ (из crazy_xray_checker)
	// Если порт закрыт, выходим за 500мс, не запуская Xray
	d := net.Dialer{Timeout: 1200 * time.Millisecond}
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
	minSuccess := 2
	if shouldUseFastMode() {
		minSuccess = 1
	}
	successCount := 0
	appLikeSuccess := 0
	bestLatency := 0

	for i, target := range activeProbeTargets() {
		latency := probeTargetWithFallbackUA(client, target, timeout, time.Now().UnixNano()+int64(i))
		if latency <= 0 {
			continue
		}
		successCount++
		if appLikeTargets[target] {
			appLikeSuccess++
		}
		if bestLatency == 0 || latency < bestLatency {
			bestLatency = latency
		}
		if successCount >= minSuccess && appLikeSuccess >= 1 {
			return bestLatency
		}
	}
	if successCount >= minSuccess {
		return bestLatency
	}

	return 0
}

func main() {}
