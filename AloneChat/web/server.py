import http.server
import json
import logging
import os
import socketserver
import sys
from pathlib import Path

PORT = 9007

# 配置日志
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def load_config():
    """Load configuration from a JSON file."""
    config_path = Path(__file__).parent / 'config.json'
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning(f"Config file {config_path} not found, using default configuration.")
        return {
            "server": {
                "host": "localhost",
                "http_port": 9007,
                "ws_port": 8765,
                "ws_path": ""
            }
        }

    except json.JSONDecodeError as e:
        logger.error(f"Error at config file: {e}")
        sys.exit(1)


class SimpleHandler(http.server.SimpleHTTPRequestHandler):
    """Process HTTP GET requests for static files."""

    def do_GET(self):
        if self.path is not None:
            if self.path == '/':
                self.path = 'index.html'

            if self.path[0] == '/':
                self.path = self.path[1:]

            try:
                # Check if the requested file exists
                if not os.path.exists('./AloneChat/web/static/' + self.path):
                    raise FileNotFoundError

                # Read and send the requested file
                with open('./AloneChat/web/static/' + self.path, 'rb') as file:
                    self.send_response(200)
                    self.send_header('Content-type', 'text/html')
                    self.end_headers()
                    self.wfile.write(file.read())

            except FileNotFoundError:
                # Raise 404 error if files not found
                self.send_error(404, "File Not Found", f"{self.path} not found in directory")
            except Exception as e:
                # Raise 500 error for any other exceptions
                self.send_error(500, f"Server Error: {str(e)}")


def server(port=None):
    # Create the server
    if port is None:
        port = PORT

    # noinspection PyTypeChecker
    with socketserver.TCPServer(("", port), SimpleHandler) as httpd:
        print(f"Serving at http://localhost:{port}")
        print("Press Ctrl+C to stop server...")
        try:
            # Start the server
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped.")
            sys.exit(0)


if __name__ == '__main__':
    server()
