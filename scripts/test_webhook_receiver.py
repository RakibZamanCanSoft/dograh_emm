import uvicorn
from fastapi import FastAPI, Request
import json
import datetime

app = FastAPI()

@app.post("/receive-data")
async def receive_webhook(request: Request):
    print("\n" + "="*60)
    print(f"🚀 WEBHOOK RECEIVED AT {datetime.datetime.now().strftime('%H:%M:%S')}")
    print("="*60)
    
    try:
        body = await request.json()
        print("\n📦 Payload from Dograh:\n")
        print(json.dumps(body, indent=4))
    except Exception as e:
        print(f"❌ Error parsing JSON: {e}")
        
    print("\n" + "="*60 + "\n")
    return {"status": "success", "message": "Data received by test website backend"}

if __name__ == "__main__":
    print("="*60)
    print("🌐 TEST WEBHOOK RECEIVER STARTED")
    print("="*60)
    print("\nIn your Dograh Webhook Node, use this exact URL:")
    print("👉 http://127.0.0.1:8001/receive-data\n")
    print("Waiting for webhooks from Dograh...\n")
    uvicorn.run(app, host="0.0.0.0", port=8001)
