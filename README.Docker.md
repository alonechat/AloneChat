# Building and running AloneChat server with Docker Compose

First ensure docker and docker compose are installed on your machine.

When you're ready, start AloneChat server by running:
`docker compose up --build`.

AloneChat server will be available at http://localhost:8766.

Then you can run client:

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt

python . client
```

Very easy one.