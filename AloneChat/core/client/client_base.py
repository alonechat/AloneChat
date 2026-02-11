class Client:
    """
    Base client class providing core websocket client functionality.
    """

    def __init__(self, host: str = "localhost", port: int = 8766):
        """
        Initialize client with connection parameters.

        Args:
            host (str): Server hostname to connect to
            port (int): Server port number
        """
        self.host = host
        self.port = port

    def run(self):
        """
        Abstract method to start the client.
        Must be implemented by subclasses.
        """
        return NotImplementedError