from data_models.sample import CurrencyReport


from fastapi import FastAPI
app = FastAPI()


app = FastAPI(title="MyTaskManager")
today_usd=CurrencyReport(datetime="10.8.2025", currency="usd",value=300)

@app.get("/")
def read_root():
    return {"message": "Welcome to MyTaskManager!"}



@app.get("/today-USD")
def return_today_usd():
    return today_usd

@app.get("/today/EUR")
def return_today_eur():
    return{299}
