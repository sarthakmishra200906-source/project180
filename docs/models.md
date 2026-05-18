# Final 5 Model List — Project 180 (Cheeku)

This file documents the cloud-first + offline model strategy for Cheeku.

## Cloud Kings (Primary Software Brains)

1. Google Gemini 2.5 Flash
   - Type: Cloud API via Google AI Studio
   - What it does for Cheeku: Primary personality + advanced conversational responses.

2. Qwen 2.5 Coder 1.5B (or 3B)
   - Type: Local / Cloud Hybrid (Ollama)
   - What it does for Cheeku: Fast code/debug assistant for firmware and server work.

## Offline Warriors (Local Ollama models)

3. Llama 3.2 1B
   - Type: Truly Offline (Ollama)
   - Use: Fast fallback brain when the network is down.

4. Qwen 2.5 1.5B (or Qwen 3.5 2B)
   - Type: Truly Offline (Ollama)
   - Use: Best offline conversational/JSON parsing model.

5. Gemma 4 E2B (Edge-Optimized MoE)
   - Type: Truly Offline (Ollama)
   - Use: Upgrade-path model with improved reasoning and tool-calling.

## Pull commands (one-liners you can run on the laptop)

ollama pull llama3.2:1b
ollama pull qwen2.5:1.5b
ollama pull gemma4:e2b


---
Saved from the project chat. Keep this file in `docs/` for future reference.
