# 🚀 Deploying Delentia SLM Backend on Hugging Face Nvidia L4

This folder provides a complete FastAPI web server wrapper to serve fine-tuned Delentia Guardian/Router adapters on Hugging Face Spaces using dedicated **Nvidia L4 GPU (24GB VRAM)** hardware.

---

## 🛠️ Step-by-Step Deployment on Hugging Face Spaces

1. **Create a New Space**:
   * Go to Hugging Face ➔ **New Space**.
   * Enter your space name (e.g. `delentia-l4-backend`).
   * Select **Docker** as the SDK.
   * Choose **Blank** template.

2. **Select Space Hardware**:
   * Under Space settings or initialization, choose **Nvidia L4 (Medium)** hardware.

3. **Configure Space Secrets**:
   * Add the following **Secrets** in Space settings:
     * `RCT_CORE_BRAIN_KEY`: Define a secure key that matches the client key (e.g., `s3cr3t_br41n_k3y`).
     * `HF_TOKEN`: A Hugging Face Write access token to allow downloading private fine-tuned adapters (e.g. `Delentia/delentia-guardian-adapter-v1.3`).

4. **Upload files**:
   * Upload `Dockerfile` and `backend_main.py` directly into the Space repository root.
   * The space will automatically build the image and load the model on CUDA.

---

## 🔗 Client-Side Integration

To route requests from your main Space (Trace Console UI) to this backend, update your `openrouter_client.py` or use the following integration helper:

```python
import aiohttp
import os

class DelentiaL4Client:
    def __init__(self, backend_url: str = "https://delentia-l4-backend.hf.space"):
        # Make sure to change backend_url to your actual Space URL
        self.url = f"{backend_url.rstrip('/')}/v1/generate"
        self.brain_key = os.getenv("RCT_CORE_BRAIN_KEY", "default_secret_key")

    async def generate_completion(self, prompt: str, temp: float = 0.2, max_tokens: int = 512) -> str:
        headers = {
            "Content-Type": "application/json",
            "X-RCT-Brain-Key": self.brain_key
        }
        payload = {
            "prompt": prompt,
            "temperature": temp,
            "max_tokens": max_tokens
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(self.url, json=payload, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    return data["response"]
                else:
                    error_text = await response.text()
                    raise Exception(f"Backend API Error ({response.status}): {error_text}")
```
