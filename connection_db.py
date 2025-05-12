from fastapi import FastAPI, HTTPException, status, Body
from azure.cosmos import CosmosClient
from pydantic import BaseModel
from typing import List
import uuid
import json
import os

from dotenv import load_dotenv
load_dotenv() 

# Dane do połączenia z database
url = "https://baza.documents.azure.com:443/"
key = os.getenv("COSMOSDB_KEY")

client = CosmosClient(url, credential=key)

# Połączenie z bazą i kontenerami
db = client.get_database_client("Baza")
db_users = db.get_container_client("Users")
db_records = db.get_container_client("Records")

# FastAPI app
app = FastAPI(title="Aplikacja do zarządzania budżetem", description="Backend do odczytu rekordów z database")

# Model odpowiedzi z bazy danych
class Users(BaseModel):
    id: str
    id_user: str
    name_user: str
    password_user: str

class Records(BaseModel):
    id: str
    id_record: str
    data: str
    jedzenie: str
    transport: str
    rozrywka: str
    rachunki: str
    zdrowie: str
    dom: str
    ubrania: str
    inne: str

# Model danych wejściowych do logowania
class LoginRequest(BaseModel):
    name_user: str
    password_user: str

class CreateRequest(BaseModel):
    name_user: str
    password_user: str

#Endpoint logowania
@app.post("/login")
def login(request: LoginRequest):
    query = "SELECT * FROM Users u WHERE u.name_user = @name_user"
    parameters = [{"name": "@name_user", "value": request.name_user}]
    user_result = list(db_users.query_items(query=query, parameters=parameters, enable_cross_partition_query=True))

    if not user_result:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Nieprawidłowy użytkownik lub hasło")

    user = user_result[0]

    if user["password_user"] != request.password_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Nieprawidłowy użytkownik lub hasło")

    return {"message": "Zalogowano pomyślnie", "user": user["id_user"]}

#Endpoint stwórz nowe konto
@app.post("/register_user")
def register_user(user: CreateRequest):
    #Sprawdza czy istnieje taki użytkownik
    query = "SELECT * FROM Users u WHERE u.name_user = @name_user"
    parameters = [{"name": "@name_user", "value": user.name_user}]

    existing_users = list(db_users.query_items(
        query=query,
        parameters=parameters,
        enable_cross_partition_query=True
    ))

    if existing_users:
        raise HTTPException(status_code=400, detail="Użytkownik o tej nazwie już istnieje.")

    new_id = str(uuid.uuid4())
    new_user = {
        "id": new_id,
        "id_user": new_id,
        "name_user": user.name_user,
        "password_user": user.password_user  # w realnej aplikacji: zahaszuj hasło!
    }

    db_users.create_item(body=new_user)

    return {"message": "Użytkownik zarejestrowany", "user_id": new_id}

# Endpoint: pobierz rekordy użytkownika
@app.get("/records/{user_id}", response_model=List[Records])
def get_records(user_id: str):
    query = "SELECT * FROM Records r WHERE r.id_user = @id_user"
    parameters = [{"name": "@id_user", "value": user_id}]
    items = db_records.query_items(query=query, parameters=parameters, enable_cross_partition_query=True)
    return list(items)


# Endpoint: aktualizowanie budżetu, sprawdza czy istnieje dany rekord (nazwa user i dzień miesiaca) pobiera i nadpisuje budżet
@app.post("/update_budget/{id_user}/{data}")
def update_budget(id_user: str, data: str, new_budget: dict = Body(...)):
    #Szukamy istniejącego rekordu
    query = "SELECT * FROM Rekords r WHERE r.id_user = @id_user AND r.data = @data"
    parameters = [
        {"name": "@id_user", "value": id_user},
        {"name": "@data", "value": data}
    ]

    items = list(db_records.query_items(
        query=query, 
        parameters=parameters, 
        enable_cross_partition_query=True)
    )

    if items:
        #Rekord istnieje aktualizujemy
        record = items[0]
        record_id = record["id"]

        for key, value in new_budget.items():
            if key in record:
                try:
                    record[key] = str(float(record[key]) + float(value))
                except ValueError:
                    raise HTTPException(status_code=400, detail=f"Nieprawidłowa wartość w polu '{key}'")
        db_records.replace_item(item=record_id, body=record)
        return {"message": "Rekord zaktualizowany", "record": record}
    
    else: 
        #Rekord nie istnieje, tworzymy nowy
        new_id = str(uuid.uuid4())
        new_record = {
            "id": new_id,
            "id_record": new_id,
            "id_user": id_user,
            "data": data,
            "jedzenie": "0",
            "transport": "0",
            "rozrywka": "0",
            "rachunki": "0",
            "zdrowie": "0",
            "dom": "0",
            "ubrania": "0",
            "inne": "0",
            **new_budget  # nadpisz wartości jeśli są
        }
        print("DEBUG: zapisuję:", json.dumps(new_record, indent=2))
        db_records.create_item(body=new_record)
        return {"message": "Rekord utworzony", "record": new_record}
    
# Endpoint home
@app.get("/")
def home():
    return {"message": "Hello, Azure!"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("connection_db:app", host="127.0.0.1", port=8000, reload=True)
