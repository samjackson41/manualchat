# Mobile and on-device deployment

This document records an exploration of two future directions for ManualChat. It does not ratify a decision, and it changed no code. The directions are a mobile app that uses the same backend, and a model that runs on-device. On-device means the model runs on the phone itself, with no server.

## The parts that matter

The backend is a plain HTTP service. It returns JSON and streams text, so a phone app can call it as-is.

`backend/llm.py` is the only file that calls a model service. Today that service is OpenRouter. The agent graph and the tools all go through this file.

The document search already runs on one machine with no network. Two small models do the search: an embedder that turns text into a list of numbers, and a reranker that orders the results. The vector index lives in a directory on disk (Qdrant local mode). Only the model call leaves the machine.

Ingest is the heavy step. It turns a PDF into text and tables with Docling. The deployment plan already moves ingest into a separate job, away from the serving image. See [DEPLOYMENT.md](DEPLOYMENT.md).

## Mobile app, same backend

A mobile app is a change to the client, not the backend. A progressive web app (PWA) is a site that the phone adds to its home screen, with no app store. Four options follow, in order of effort.

| Approach | Effort | Notes |
|---|---|---|
| Responsive web or PWA | days | Reuse the current page. No app store. PDF display on mobile is the main risk. |
| Capacitor wrapper | about a week | Reuse the current page in a native shell, ship to the app store, and capture files and photos natively. |
| React Native or Expo | weeks | Reuse the API client and the app state, but write the screens natively. |
| Native SwiftUI or Kotlin | weeks to months | The best fit for the platform. This is the only option that uses Apple's on-device APIs fully. |

Every option needs three things: an account system (not the shared API key), HTTPS, and a choice for PDF display on the phone. The PDF viewer is the biggest mobile risk, more than the chat or the API.

Recommendation: start with the responsive PWA to learn the mobile needs for free, then wrap it in Capacitor to reach the app store fast. Use React Native for a long-term app. Choose SwiftUI only if you commit to on-device.

## A local model on one machine

Two targets exist. Do not confuse them.

### On a server

Keep the whole backend, and point `llm.py` at a local model server that speaks the same chat API. Choose llama.cpp, Ollama, vLLM, or MLX-LM. This is one configuration change. A small adapter is also needed, because local servers treat some parameters (such as `reasoning_effort`) differently and return tool calls in a different shape.

The search and the index already run locally, so this change makes the app run with no cloud at all.

### On the phone

Break the app into parts by weight.

The search moves easily. The embedder and the reranker are small, and one manual holds a few thousand vectors. In-memory search, or SQLite with a vector extension (sqlite-vec), is enough. Qdrant is not needed.

The model needs testing more than a rewrite. The loop is bounded. The supervisor prints one word. The worker picks from four tools, and each tool argument is simple (a query string, a subject, page numbers). Small models such as Qwen2.5 3B and Llama 3.2 3B handle this, and Qwen2.5 supports function calling out of the box. You can also constrain the output so the tool calls stay valid. The real risk is the final answer: a small model follows the grounding rules less well and invents facts more than a large one. The eval harness measures exactly this. Test it instead of assuming it fails. You can keep the two-model split with a small routing model and a larger answer model.

Ingest stays hardest to move. Docling needs heavy hardware. Apple PDFKit reads text from born-digital PDFs, and VisionKit reads scanned text, but table reconstruction belongs in the cloud. The plan already treats ingest as a separate job, so the natural shape is cloud ingest and on-device search.

A middle path exists: keep the search on the phone and the model in the cloud or on a local server.

## The offline package

One fact makes the offline path easier. The deployment plan already defines a package for a processed manual. The zip from Milestone 2 in [DEPLOYMENT.md](DEPLOYMENT.md) holds the PDF, the page text, the tables, the chunks, and the vectors. The offline app downloads that zip once, or ships it bundled, and then needs no ingest. It still runs the embedder and the reranker on the phone, but not Docling. The vectors in the zip save the work of indexing the whole manual; the app only embeds each new question.

## iPhone 16 and Apple Intelligence

This is possible, with one limit.

Apple Intelligence is not a general API for running your own model. The user-facing features, such as Writing Tools, Siri, and summaries, are not a chat backend for your app.

iOS 26 shipped the Foundation Models framework, the first public on-device model API for third-party apps. It offers a language model of about three billion parameters, text in a fixed shape (structured output), and embeddings. It also supports bringing your own model and small adapters. A LoRA adapter is a small extra model that changes behavior without a full retrain. The framework runs on the phone's neural engine.

Independent of Apple, a small open model runs through Core ML, llama.cpp, or MLX Swift. Examples are Llama 3.2 3B, Qwen2.5 1.5B and 3B, Phi-3.5, and Gemma 3.

The limit is accuracy, not feasibility. The product promise is grounded, cited answers. The eval gate needs citation precision of 0.9 or more and a pass rate of 0.8 or more. A small model follows instructions worse and invents facts more than DeepSeek V4 Pro. Measure before you commit.

## Building the iOS app

Build it in Swift with SwiftUI, natively. The on-device model tools (Core ML, MLX Swift, the Foundation Models framework, and PDFKit for the viewer) are Swift APIs, and the app is iOS-only, so native is the shortest path. React Native adds a bridge to the same Swift code, which helps only if you share the app with Android. You already have the web app as the design reference; port the logic, not the code. The graph becomes a small state machine in Swift, and the search becomes a few lines over a local index.

For the model, start with llama.cpp in GGUF format. It has the most iOS examples and the widest model choice. MLX Swift is the Apple-native alternative. The Foundation Models framework model needs no download, but you control it less.

## Examples by others

These projects show the pieces working offline on iPhone. The names come from search results, so check each one before you rely on it.

- llama.cpp runs on iOS with Metal acceleration.
- MLX Swift (`ml-explore/mlx-swift` on GitHub) includes iOS example apps.
- SwiftChat (AlfianLosari on GitHub) shows a SwiftUI chat with llama.cpp models.
- LlamaKit and llama.rn wrap llama.cpp for Swift and for React Native.
- Transformers.swift from Hugging Face runs models with Core ML.
- USearch and sqlite-vec provide local vector search.
- Private LLM, LLMFarm, and Quivr run a local model or local documents on iPhone.

The common recipe matches ManualChat's search stage: a small embedding model, a local vector index, and a llama.cpp model, all offline.

## Recommendation

Run the phases in this order:

- Measure first. Point `llm.py` at a local model of about three billion parameters, and run the eval harness in `backend/eval/`. This gives a real accuracy number in about a day.
- Ship a mobile client. Start with a PWA, then Capacitor, on the existing backend. Add accounts.
- Go local on a server. Swap OpenRouter for a local chat server. This is one configuration change.
- Move to hybrid. Put the search on-device, and keep the answer model in the cloud or on a local server.
- Go full on-device last. A native Swift app with a llama.cpp or MLX model, one search step, cloud ingest, and the offline package from Milestone 2.

## Sources

The Apple facts above are newer than this project's knowledge cutoff. Make sure that they are still current in Apple's developer documentation (the Foundation Models framework) before you depend on them. The web search returned summaries, not stable links. The example projects in the list also need a current check.

Last checked: 2026-11-11.
