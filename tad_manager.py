import pandas as pd
from sqlalchemy import create_engine
from api_keys import news_database



def manually_add_tad(ticker: str, tad: str):
    STOCKS_DB_URL = f"mysql+pymysql://root:{news_database}@127.0.0.1:3306/stocks"
    engine = create_engine(STOCKS_DB_URL, pool_pre_ping=True, connect_args={"connect_timeout": 5})
    current_df = pd.read_sql_table("target_action_dates", engine)
    
    current_df = pd.concat([current_df, pd.DataFrame({'ticker': [ticker], 'tad': [tad]})])
    current_df.to_sql("target_action_dates", engine, if_exists="append", index=False)
    print(f"Added ticker: {ticker} with tad: {tad}")
    

def manually_remove_tad(ticker: str, tad: str):
    STOCKS_DB_URL = f"mysql+pymysql://root:{news_database}@127.0.0.1:3306/stocks"
    engine = create_engine(STOCKS_DB_URL, pool_pre_ping=True, connect_args={"connect_timeout": 5})
    current_df = pd.read_sql_table("target_action_dates", engine)
    current_df = current_df.loc[(current_df.ticker != ticker) & (current_df.tad != tad)]
    current_df.to_sql("target_action_dates", engine, if_exists="replace", index=False)
    print(f"Removed ticker: {ticker} with tad: {tad}")
    

