FROM python:3.11-slim

WORKDIR /app
COPY agent.py /app

RUN pip install flask requests

EXPOSE 9200
CMD ["python", "agent.py"]

