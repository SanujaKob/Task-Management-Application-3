# main.py

from fastapi import FastAPI

app = FastAPI(title="MyTaskManager")

@app.get("/")
def read_root():
    return {"message": "Welcome to MyTaskManager!"}



@app.get("/today-USD")
def return_today_usd():
    return{"18.8.2025":300}

@app.get("/today/EUR")
def return_today_eur():
    return{299}