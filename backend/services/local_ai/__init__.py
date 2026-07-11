"""Local AI setup — hardware detection, model selection, and install flow.

The offline/no-cloud fallback path: detect the machine, pick the best two
Ollama models it can run (quality = overnight, fast = interactive), and pull
them after explicit confirmation. Runtime never needs the network; the cloud
waterfall (services/providers/) is a separate subsystem and is never a
fallback for this path.
"""
