import importlib
import os
import time
import unittest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

class CommandSocketTests(unittest.TestCase):
    def test_mdi_text_nonce_replay_expiry_and_estop(self):
        with patch.dict(os.environ,{"FOAM_TOKEN":"x"*32,"FOAM_ORIGINS":"http://testserver"}):
            import server.main as gateway
            gateway=importlib.reload(gateway)
            rpc=AsyncMock(return_value={"ok":True,"data":{}})
            with patch.object(gateway,"rpc",rpc),TestClient(gateway.app) as client:
                with client.websocket_connect("/ws",headers={"origin":"http://testserver"}) as ws:
                    ws.send_json({"token":"x"*32,"read_only":False})
                    self.assertEqual(ws.receive_json()["type"],"ready")
                    token=ws.receive_json()["command_token"]
                    def ack(id):
                        while True:
                            message=ws.receive_json()
                            if message["type"]=="ack" and message["id"]==id:return message
                    ws.send_json({"cmd":"mdi","text":"G90","id":"1","command_token":token})
                    self.assertTrue(ack("1")["ok"])
                    forwarded=[c.args[0] for c in rpc.call_args_list if c.args[0]["cmd"]=="mdi"]
                    self.assertEqual(forwarded[0]["text"],"G90")
                    ws.send_json({"cmd":"mdi","text":"G91","id":"2","command_token":token})
                    self.assertFalse(ack("2")["ok"])
                    ws.send_json({"cmd":"estop","id":"3"})
                    self.assertTrue(ack("3")["ok"])
                    message=ws.receive_json()
                    while message["type"]!="status":
                        message=ws.receive_json()
                    stale=message["command_token"]
                    time.sleep(1.1)
                    ws.send_json({"cmd":"enable","id":"4","command_token":stale})
                    self.assertFalse(ack("4")["ok"])
                    self.assertEqual(len([c for c in rpc.call_args_list if c.args[0]["cmd"]=="mdi"]),1)
                    self.assertFalse(any(c.args[0]["cmd"]=="enable" for c in rpc.call_args_list))

if __name__=="__main__":unittest.main()
