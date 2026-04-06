# VPN Routing via nordlynx SOCKS5 Gateway

This app routes all outbound traffic through the nordlynx WireGuard VPN pod using a
SOCKS5 proxy. This document explains how the pattern works and how to apply it to
other apps in the cluster.

## How it works

The `nordlynx` pod runs two containers:

```
nordlynx pod (namespace: nordlynx)
├── nordlynx    — WireGuard VPN tunnel (all traffic exits through NordVPN)
└── microsocks  — SOCKS5 proxy listening on port 1080
```

Because both containers share the same network namespace inside the pod, microsocks
inherits the WireGuard routing. Any connection made through the proxy exits via the VPN.

The nordlynx Service exposes the proxy at a stable cluster-internal DNS address:

```
nordlynx.nordlynx.svc.cluster.local:1080
```

## How this app uses it

The `SOCKS5_PROXY_URL` environment variable is set in [k8s/deployment.yaml](k8s/deployment.yaml):

```yaml
env:
  - name: SOCKS5_PROXY_URL
    value: socks5://nordlynx.nordlynx.svc.cluster.local:1080
```

The scraper passes this to Playwright's browser launch options, routing all browser
traffic through the proxy.

To disable VPN routing (e.g. for debugging), remove or comment out the `SOCKS5_PROXY_URL`
env var and redeploy.

---

## Using this pattern in another app

Any app in the cluster can route through the VPN. The nordlynx pod acts as a shared
gateway — you do not need to run a separate VPN instance per app.

### Requirements

Your app must support SOCKS5 proxying. Most HTTP clients do via environment variables
or explicit proxy configuration.

### Step 1 — Add the env var to your deployment

```yaml
env:
  - name: SOCKS5_PROXY_URL
    value: socks5://nordlynx.nordlynx.svc.cluster.local:1080
```

### Step 2 — Use the proxy in your app

**Python (requests library)**:
```python
import os
proxies = {"http": os.getenv("SOCKS5_PROXY_URL"), "https": os.getenv("SOCKS5_PROXY_URL")}
response = requests.get("https://example.com", proxies=proxies)
```

**Python (Playwright)**:
```python
import os
browser = await playwright.chromium.launch(proxy={"server": os.getenv("SOCKS5_PROXY_URL")})
```

**curl**:
```bash
curl --proxy "$SOCKS5_PROXY_URL" https://example.com
```

**Node.js (axios + socks-proxy-agent)**:
```js
const { SocksProxyAgent } = require('socks-proxy-agent')
const agent = new SocksProxyAgent(process.env.SOCKS5_PROXY_URL)
axios.get('https://example.com', { httpsAgent: agent })
```

### Step 3 — Verify VPN routing

Exec into your pod and check the exit IP:

```bash
kubectl exec -n <namespace> deploy/<app> -- curl -s https://ifconfig.me
```

If the IP matches a NordVPN server (not your home IP), routing is working.

---

## Troubleshooting

**Connection refused on port 1080**
- Verify nordlynx pod is running: `kubectl get pods -n nordlynx`
- Verify microsocks container is ready: `kubectl logs -n nordlynx deploy/nordlynx -c microsocks`

**Traffic not going through VPN**
- Check nordlynx VPN connection: `kubectl logs -n nordlynx deploy/nordlynx -c nordlynx`
- Confirm exit IP as above

**DNS not resolving inside pod**
- The cluster DNS (`*.svc.cluster.local`) requires the pod to be in the same cluster
- Verify with: `kubectl exec -n <namespace> deploy/<app> -- nslookup nordlynx.nordlynx.svc.cluster.local`
