import asyncio
import importlib
import os
import unittest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

class PreviewHTTPTests(unittest.TestCase):
    def test_auth_size_and_adapter_payload(self):
        with patch.dict(os.environ, {"FOAM_TOKEN":"x"*32,"FOAM_ORIGINS":"http://testserver"}):
            import server.main as gateway
            gateway=importlib.reload(gateway)
            response={"ok":True,"data":{"segments":[],"frame":"machine","units":"mm"}}
            rpc=AsyncMock(return_value=response)
            with patch.object(gateway,"rpc",rpc),TestClient(gateway.app) as client:
                self.assertEqual(client.post("/preview",content="M2").status_code,401)
                self.assertEqual(rpc.await_count,0)
                headers={"Authorization":"Bearer "+"x"*32,"Origin":"http://testserver"}
                self.assertEqual(client.post("/preview",content="x"*(256*1024+1),headers=headers).status_code,422)
                self.assertEqual(rpc.await_count,0)
                self.assertEqual(client.post("/preview",content="G21 G90\nG0 X0 Y0 U0 V0\nM2",headers=headers).status_code,200)
                call=rpc.call_args.args[0]
                self.assertEqual(call["cmd"],"preview")
                self.assertIn("U0 V0",call["text"])
                self.assertEqual(client.post("/preview",content="M2",headers={**headers,"Origin":"http://wrong"}).status_code,403)

    def test_adapter_error_not_partial_success(self):
        import server.main as gateway
        with patch.object(gateway,"TOKEN","x"*32),patch.object(gateway,"ALLOWED",{"http://testserver"}):
            with patch.object(gateway,"rpc",AsyncMock(return_value={"ok":False,"error":"G2/G3 unsupported"})):
                with TestClient(gateway.app) as client:
                    result=client.post("/preview",content="G2 X1",headers={"Authorization":"Bearer "+"x"*32})
                    self.assertEqual(result.status_code,422)
                    self.assertFalse(result.json()["ok"])

if __name__=="__main__":unittest.main()
