# External integration setup

External integrations are optional. The companion does not open a network connection until
you enable one in **Settings → Integrations**. Clipboard tracking, Automatic Tracking, the
Full Map, and the Mini Map continue to work without a connection.

The first integration version supports:

- Receiving friends or group members as temporary player points.
- Receiving temporary external markers and shared waypoints.
- Sharing your active waypoint, if you opt in.
- Sharing your precise current X/Y/Z position, if you separately opt in.

External points are kept only in memory. Disconnecting removes them, and they are never added
to the local custom-marker file.

## Join an existing server or friend group

Ask the server owner for four values:

1. The secure WebSocket URL, normally `wss://...`.
2. The room name.
3. The access token, if the service requires one.
4. Confirmation that the service supports Gateway `0.21.772` and protocol version 1.

Then in The Isle Companion:

1. Open **Settings → Integrations**.
2. Enter a recognizable service name.
3. Enter the WebSocket URL, room, your display name, and access token.
4. Select **Show external players, waypoints, and markers**.
5. Select **Share my active waypoint** only if you want others to receive it.
6. Select **Share my precise current position while connected** only if you understand and
   want that disclosure.
7. Select **Enable the configured external connection**, then save.
8. Check the status bar for `External integrations: connected to ...`.
9. In the Full Map Layers panel, leave **External integrations** enabled.

The **External Connection** toolbar control is an immediate connection switch. Turning it off
disconnects the service and clears its temporary points without deleting the saved profile.

## Quick local test on one computer

The repository includes a small reference room relay. It uses the same PySide6 installation as
the desktop app.

In PowerShell:

```powershell
$env:TIC_RELAY_TOKEN = "replace-this-with-a-long-random-token"
py tools\integration_relay.py
```

On Linux:

```bash
export TIC_RELAY_TOKEN='replace-this-with-a-long-random-token'
python tools/integration_relay.py
```

Configure the companion with:

- URL: `ws://127.0.0.1:8765`
- Room: any shared name such as `test-pack`
- Access token: the value assigned to `TIC_RELAY_TOKEN`

`ws://` is intentionally accepted only for `localhost`, `127.0.0.1`, and `::1`. A connection
that leaves the computer must use encrypted `wss://`.

## Host a relay for friends

The included relay is deliberately small and is most suitable as a reference deployment for a
trusted group. It provides room isolation, bearer-token access, strict message validation, and
no database. It does not provide user accounts, moderation, revocation lists, or an admin UI.

### 1. Prepare the application

Clone the project on a server with Python 3.11 or newer, create a virtual environment, and
install the normal requirements:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Generate a long random token with your password manager. Do not reuse a personal password.
Keep the relay bound to loopback so only the TLS reverse proxy can reach it:

```bash
export TIC_RELAY_TOKEN='your-long-random-token'
python tools/integration_relay.py --host 127.0.0.1 --port 8765
```

The token can also be passed with `--token`, but an environment variable is preferable because
command-line arguments may be visible to other processes on the server.

### 2. Put it behind TLS

Point a DNS name at the server and terminate TLS with your existing reverse proxy. For example,
a minimal Caddy configuration is:

```caddyfile
companion.example.com {
    reverse_proxy 127.0.0.1:8765
}
```

Caddy's reverse proxy supports the WebSocket upgrade and a domain site address enables its
automatic HTTPS behavior. Keep ports 80 and 443 reachable as required by your certificate and
hosting setup. See the official [Caddy reverse proxy documentation](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy)
and [HTTPS quick start](https://caddyserver.com/docs/quick-starts/https).

Do not expose port 8765 publicly. Users should connect to:

```text
wss://companion.example.com
```

### 3. Give friends the connection profile

Share the following through a trusted channel:

- The `wss://` URL.
- The access token.
- A room name agreed by the group.

Everyone in one group must enter the same room exactly. Different room names do not receive one
another's points. Each person chooses their own display name and permissions.

For a public or multi-community deployment, build authentication, authorization, rate limits,
observability, moderation, and token rotation around the documented protocol rather than
treating the reference relay as a complete hosted product.

## Integrate an existing website or community service

Implement a WebSocket endpoint that follows
[`integration-protocol-v1.md`](integration-protocol-v1.md). The desktop app always initiates the
connection, so the service does not need access to the user's computer or local network.

At minimum, a service must:

1. Authenticate the WebSocket request if access is restricted.
2. Wait for `hello` and reply with `welcome`.
3. Grant only capabilities that the client requested and the user is authorized to use.
4. Preserve the Gateway map identity and world-coordinate space in every envelope.
5. Convert player updates into `feature.upsert` messages for authorized room members.
6. Send `feature.remove` on disconnect and give live player points a short expiry.
7. Validate and rate-limit all messages; never rebroadcast unvalidated client JSON.

The desktop app currently accepts external point features only. Polygon and circle zones are
reserved for a later protocol capability.

## Troubleshooting

- **Connection requires wss://**: the URL is remote and unencrypted. Add a TLS reverse proxy.
- **Handshake timed out**: the endpoint accepted the socket but did not return a valid `welcome`
  within ten seconds.
- **Map ... does not match**: the server and app are using different map manifests or versions.
- **Connected but nothing appears**: enable point reception, ensure other users share their
  position, use the same room, and enable the External integrations layer.
- **Players appear and disappear**: live player features expire after 15 seconds, and the client
  stops refreshing a locally observed position after it becomes stale. Check that the publishing
  client continues receiving local coordinate updates and remains connected.
- **Invalid access token**: make sure there are no extra spaces and that the relay and client use
  the same token.
