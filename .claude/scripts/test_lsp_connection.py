#!/usr/bin/env python3
"""测试 multilspy LSP 连接"""

from multilspy import SyncLanguageServer
from multilspy.multilspy_config import MultilspyConfig
from multilspy.multilspy_logger import MultilspyLogger
from pathlib import Path

config_dict = {
    "code_language": "python",
    "lsp_server": {
        "command": "pyright-langserver",
        "args": ["--stdio"],
        "initializationOptions": {},
    },
}

config = MultilspyConfig.from_dict(config_dict)
logger = MultilspyLogger()

try:
    lsp = SyncLanguageServer.create(config, logger, str(Path.cwd()))
    print("LSP server created successfully")

    # 尝试启动服务器
    with lsp.start_server():
        print("LSP server started successfully")

        # 测试 document symbols
        test_file = "packages/datahub/src/ditto_datahub/accessors/adj_factor.py"
        result = lsp.request_document_symbols(test_file)
        print(f"Document symbols result: {result[:2] if result else 'None'}")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
