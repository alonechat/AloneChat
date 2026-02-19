# syntax=docker/dockerfile:1

# Comments are provided throughout this file to help you get started.
# If you need more help, visit the Dockerfile reference guide at
# https://docs.docker.com/go/dockerfile-reference/

# Want to help us make this template better? Share your feedback here: https://forms.gle/ybq9Krt8jtBL3iCk7

ARG PYTHON_VERSION=3.13.7
FROM python:${PYTHON_VERSION}-slim as base

# Prevents Python from writing pyc files.
ENV PYTHONDONTWRITEBYTECODE=1

# Keeps Python from buffering stdout and stderr to avoid situations where
# the application crashes without emitting any logs due to buffering.
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Create a non-privileged user that the app will run under.
# See https://docs.docker.com/go/dockerfile-user-best-practices/
ARG UID=10001
RUN adduser \
    --disabled-password \
    --gecos "" \
    --home "/nonexistent" \
    --shell "/sbin/nologin" \
    --no-create-home \
    --uid "${UID}" \
    alonechat_user

# Download dependencies as a separate step to take advantage of Docker's caching.
# Leverage a cache mount to /root/.cache/pip to speed up subsequent builds.
# Leverage a bind mount to requirements.txt to avoid having to copy them into
# into this layer.
RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=bind,source=requirements.txt,target=requirements.txt \
    --mount=type=bind,source=requirements-dev.txt,target=requirements-dev.txt \
    python -m pip install -r requirements.txt && \
    python -m pip install -r requirements-dev.txt

# Create logs directory before switching user.
RUN mkdir -p /app/logs

# Copy the source code into the container with correct ownership.
COPY --chown=alonechat_user:alonechat_user . .

# Set permissions for logs directory after copy.
RUN chown -R alonechat_user:alonechat_user /app/logs

# Switch to the non-privileged user to run the application.
USER alonechat_user

# Expose the port that the application listens on.
# Only expose the port that the application listens on.
EXPOSE 8766

# This ignores tkinter, which can cause issues when running in a container without a display.

# Run the application.
CMD export PURE_SERVER_ENVIRON=true && python . server
