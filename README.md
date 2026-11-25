# DePIN Video Streaming Node

The provider node for a 2025 distributed video streaming prototype. It retrieves video by content ID, converts it to HLS with FFmpeg, and registers the resulting stream with the [FastAPI gateway](https://github.com/zephyranthes03/depin_host). The [browser frontend](https://github.com/zephyranthes03/front_depin_host) uses the gateway's stream registry to find providers.

## Local setup

Install Python 3.10 or later, FFmpeg, and the IPFS CLI. The EthStorage path uses its CLI and the local environment settings referenced in [depin.py](depin.py). See [env.sample](env.sample) for the RPC setting.

~~~sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn depin:app --host 127.0.0.1 --port 8001
~~~

The [interactive API docs](http://127.0.0.1:8001/docs) show the registered endpoints. The gateway URLs and browser origin in [depin.py](depin.py) reflect the original demo configuration. Point them to your local gateway and frontend for an integrated run.

## Streaming flow

1. The node looks up video metadata by CID at the gateway.
2. It downloads the source using IPFS or EthStorage and uses FFmpeg to generate an HLS playlist and segments.
3. It serves the generated assets under `/streaming` and registers the stream URL with the gateway.

| Endpoint | Purpose |
| --- | --- |
| `POST /register` | Prepare and register an IPFS-backed stream. |
| `POST /register_web3` | Prepare and register an EthStorage-backed stream. |
| `POST /deregister` | Remove the provider's stream registration. |
| `GET /stream/{blockchain_address}/{cid}` | Serve the IPFS path's HLS playlist. |
| `GET /stream_web/{blockchain_address}/{cid}` | Serve the web storage path's HLS playlist and send a view record to the gateway. |

[app.py](app.py) contains a separate download and conversion prototype. The workflow above uses `depin.py`.

## License

[MIT](LICENSE)
