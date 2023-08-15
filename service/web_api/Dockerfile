FROM public.ecr.aws/docker/library/python:3.9-slim

COPY . .
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 80

CMD [ "flask", "run", "--host", "0.0.0.0", "--port", "80"]