"""
Delentia OS — Real Application Generator: Project 01
PromptPay Smart Billing & Dynamic EMVCo QR Code Engine
Full-Stack Standalone Web Application with Real EMVCo CRC16 Payload Calculation
"""

import os
import sys
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# EMVCo PromptPay Payload Generator (Real Math & CRC16)
def crc16_ccitt(data: str) -> str:
    crc = 0xFFFF
    for ch in data:
        crc ^= (ord(ch) << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def generate_promptpay_payload(target: str, amount: float = None) -> str:
    target = target.replace("-", "").strip()
    if len(target) == 10 and target.startswith("0"):
        target_formatted = "0066" + target[1:]
    else:
        target_formatted = target

    tag29 = f"0016A00000067701011101{len(target_formatted):02d}{target_formatted}"
    payload = f"00020101021229{len(tag29):02d}{tag29}5802TH5303764"
    if amount and amount > 0:
        amt_str = f"{amount:.2f}"
        payload += f"54{len(amt_str):02d}{amt_str}"
    
    payload_to_crc = payload + "6304"
    checksum = crc16_ccitt(payload_to_crc)
    return payload_to_crc + checksum


HTML_PAGE = """<!DOCTYPE html>
<html lang="th">
<head>
  <meta charset="UTF-8">
  <title>Delentia OS — PromptPay Smart Billing Portal</title>
  <script src="https://cdn.jsdelivr.net/npm/qrcode@1.5.1/build/qrcode.min.js"></script>
  <style>
    body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #080C14; color: #E2E8F0; margin: 0; padding: 24px; }
    .card { max-width: 650px; margin: 0 auto; background: #0F172A; border: 1px solid #1E293B; border-radius: 16px; padding: 28px; box-shadow: 0 20px 40px rgba(0,0,0,0.6); }
    h1 { color: #00F5FF; font-size: 22px; margin-top: 0; display: flex; align-items: center; gap: 8px; }
    .badge { background: #00F5FF20; color: #00F5FF; border: 1px solid #00F5FF50; padding: 3px 8px; border-radius: 6px; font-size: 11px; }
    .form-group { margin-bottom: 16px; }
    label { display: block; font-size: 12px; color: #94A3B8; margin-bottom: 6px; font-weight: bold; }
    input { width: 100%; box-sizing: border-box; padding: 12px 14px; background: #030712; border: 1px solid #334155; border-radius: 8px; color: #fff; font-size: 14px; outline: none; }
    input:focus { border-color: #00F5FF; }
    button { width: 100%; padding: 14px; background: linear-gradient(135deg, #00F5FF, #0284C7); border: none; border-radius: 8px; color: #000; font-weight: bold; font-size: 15px; cursor: pointer; transition: 0.2s; }
    button:hover { opacity: 0.9; transform: translateY(-1px); }
    #qr-container { text-align: center; margin-top: 24px; padding: 20px; background: #030712; border-radius: 12px; border: 1px solid #1E293B; display: none; }
    #qrcode canvas { border-radius: 8px; border: 6px solid #fff; }
    .payload-text { font-family: monospace; font-size: 11px; color: #38BDF8; word-break: break-all; margin-top: 12px; background: #0B1329; padding: 10px; border-radius: 6px; }
    .status-tag { display: inline-block; margin-top: 10px; color: #4ADE80; font-size: 12px; font-weight: bold; }
  </style>
</head>
<body>
  <div class="card">
    <div style="display: flex; justify-content: space-between; align-items: center;">
      <h1>💳 PromptPay Smart Billing <span class="badge">PROJ-01 REAL DELIVERABLE</span></h1>
    </div>
    <p style="font-size: 13px; color: #94A3B8; margin-bottom: 20px;">ระบบออกใบแจ้งหนี้และสร้าง QR Code มาตรฐาน EMVCo พร้อมคำนวณ Checksum CRC-16 อัตโนมัติ</p>

    <div class="form-group">
      <label>เบอร์โทรศัพท์ / เลขประจำตัวผู้เสียภาษี (PromptPay ID):</label>
      <input type="text" id="target" value="0812345678" placeholder="เช่น 0812345678 หรือ 1100500123456">
    </div>

    <div class="form-group">
      <label>ยอดเงินที่ต้องชำระ (บาท):</label>
      <input type="number" id="amount" value="350.00" step="0.01" placeholder="เช่น 350.00">
    </div>

    <div class="form-group">
      <label>บันทึกช่วยจำ / รายละเอียดสินค้า:</label>
      <input type="text" id="desc" value="ค่าผลผลิตสตอเบอร์รี่เกรด A จากฟาร์ม Delentia" placeholder="รายละเอียด">
    </div>

    <button onclick="generateQR()">⚡ สร้าง QR Code ชำระเงินจริง</button>

    <div id="qr-container">
      <div id="qrcode"></div>
      <div class="status-tag">✓ EMVCo QR Code Payload สร้างสำเร็จและสแกนได้จริง</div>
      <div class="payload-text" id="payload-display"></div>
    </div>
  </div>

  <script>
    async function generateQR() {
      const target = document.getElementById('target').value;
      const amount = parseFloat(document.getElementById('amount').value);
      
      const resp = await fetch(`/api/generate?target=${target}&amount=${amount}`);
      const data = await resp.json();
      
      const qrDiv = document.getElementById('qrcode');
      qrDiv.innerHTML = '';
      
      QRCode.toCanvas(data.payload, { width: 220, margin: 2 }, function (err, canvas) {
        if (!err) {
          qrDiv.appendChild(canvas);
          document.getElementById('payload-display').innerText = 'EMVCo Payload: ' + data.payload;
          document.getElementById('qr-container').style.display = 'block';
        }
      });
    }
  </script>
</body>
</html>
"""

class PromptPayHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/generate":
            params = urllib.parse.parse_qs(parsed.query)
            target = params.get("target", ["0812345678"])[0]
            amount = float(params.get("amount", [0])[0])
            payload = generate_promptpay_payload(target, amount)
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "SUCCESS", "payload": payload, "target": target, "amount": amount}).encode("utf-8"))
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))

def run_server(port=8081):
    server = HTTPServer(("127.0.0.1", port), PromptPayHandler)
    print(f"🚀 [PROJ-01 REAL APP ONLINE] http://localhost:{port}")
    server.serve_forever()

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8081
    run_server(port)
