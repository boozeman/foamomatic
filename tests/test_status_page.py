"""HTTP and WebSocket checks using a fake adapter; never connect to a machine."""
import importlib
import os
import unittest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

class StatusPageTests(unittest.TestCase):
    def test_page_assets_and_read_only_session(self):
        with patch.dict(os.environ, {"FOAM_TOKEN": "x" * 32,
                                    "FOAM_ORIGINS": "http://testserver"}):
            import server.main as gateway
            gateway = importlib.reload(gateway)
            rpc = AsyncMock(return_value={"ok": True, "data": {}})
            with patch.object(gateway, "rpc", rpc), TestClient(gateway.app) as client:
                page = client.get("/")
                self.assertEqual(page.status_code, 200)
                self.assertIn("Machine status", page.text)
                for asset in ("status.js", "status.css"):
                    self.assertEqual(client.get("/assets/" + asset).status_code, 200)
                with client.websocket_connect("/ws", headers={"origin": "http://testserver"}) as ws:
                    ws.send_json({"token": "x" * 32, "read_only": True})
                    self.assertTrue(ws.receive_json()["read_only"])
                    ws.send_json({"cmd": "enable"})
                    while True:
                        msg = ws.receive_json()
                        if msg["type"] == "ack":
                            self.assertFalse(msg["ok"])
                            break
                self.assertTrue(all(call.args[0]["cmd"] in {"status", "release"}
                                    for call in rpc.call_args_list))

    def test_reject_wrong_token_and_origin(self):
        import server.main as gateway
        with patch.object(gateway, "TOKEN", "x" * 32), patch.object(gateway, "ALLOWED", {"http://testserver"}):
            from starlette.websockets import WebSocketDisconnect
            with TestClient(gateway.app) as client:
                with self.assertRaises(WebSocketDisconnect):
                    with client.websocket_connect("/ws", headers={"origin": "http://wrong"}):
                        pass
                with client.websocket_connect("/ws", headers={"origin": "http://testserver"}) as ws:
                    ws.send_json({"token": "wrong", "read_only": True})
                    with self.assertRaises(WebSocketDisconnect): ws.receive_json()

if __name__ == "__main__":
    unittest.main()
