# Adapter that makes the real Foreman (external/foreman) play the `scheduler` role. See adapter.py.
FROM python:3.12-alpine
RUN apk add --no-cache docker-cli
COPY adapter.py /adapter.py
EXPOSE 8090
CMD ["python", "-u", "/adapter.py"]
