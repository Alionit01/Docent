# Taste (Continuously Learned by [CommandCode][cmd])

[cmd]: https://commandcode.ai/

# workflow
- Use read_file tool to read files instead of creating scripts (e.g., extract_spec.js) or running shell commands to process file contents. Confidence: 0.75
- When unable to parse a complex file format, ask the user for a simpler version (e.g., markdown) rather than writing extraction scripts. Confidence: 0.70

# tech-stack
- Use Groq as the LLM provider (OpenAI-compatible API via openai SDK pointed at `https://api.groq.com/openai/v1`). Confidence: 0.70
- Use ChromaDB instead of pgvector for vector storage to minimize external dependencies. Confidence: 0.70
- Use a local embedding model (e.g., all-MiniLM-L6-v2, 512-dim) instead of cloud-based embedding APIs. Confidence: 0.70
