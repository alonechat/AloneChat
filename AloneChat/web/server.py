import http.server
import json
import logging
import os
import socketserver
import sys

PORT = 9007

# 配置日志
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def load_config():
    """Load configuration from a JSON file."""
    config_path = 'AloneChat/web/static/config.json'
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning(f"Config file {config_path} not found, using default configuration.")
        return {
            "server": {
                "ws_protocol": "ws",
                "ws_host": "localhost",
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
            if "?" in self.path:
                self.path = self.path.split("?")[0]

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


def server(ws_host=None, ws_port=None, port=None):
    # Create the server
    config = load_config()

    ws_protocol = config['server']['ws_protocol'] if config['server']['ws_protocol'] is not None else "ws"
    ws_host = config['server']['ws_host'] if config['server']['ws_host'] is not None else "localhost"
    ws_port = config['server']['ws_port'] if config['server']['ws_port'] is not None else PORT
    ws_path = config['server']['ws_path'] if config['server']['ws_path'] is not None else ""

    if port is None:
        port = PORT

    if ws_host is None:
        ws_host = "localhost"

    if ws_port is None:
        ws_port = 8765

    # noinspection PyTypeChecker
    with socketserver.TCPServer(("", port), SimpleHandler) as httpd:
        print(
            f"Serving at "
            f"http://localhost:{port}/index.html?wsProtocol={ws_protocol}&wsHost={ws_host}&wsPort={ws_port}&wsPath={ws_path}"
        )
        print("Press Ctrl+C to stop server...")
        try:
            # Start the server
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped.")
            sys.exit(0)


if __name__ == '__main__':
    server()
