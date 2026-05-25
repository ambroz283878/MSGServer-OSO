# python -m venv venv
# source venv/bin/activate
# pip install -r requirements.txt 
# docker-compose -f ./compose-postgresql.yaml up -d

# cat ./create_db.psql | docker exec -i msgserver-oso_postgres_1 psql -h localhost -U postgres -f-

# openssl genrsa -out private.pem 2048
# openssl rsa -in private.pem -pubout -out public.pem