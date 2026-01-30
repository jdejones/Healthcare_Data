from sec_api import FullTextSearchApi, QueryApi, RenderApi
import pandas as pd
from datetime import datetime
from tqdm import tqdm
import tiktoken
import re
from bs4 import BeautifulSoup
from openai import OpenAI
from sqlalchemy import create_engine, MetaData, Table, Column, String, Date
import os
import sys
from dateparser.search import search_dates


MAX_TOKENS = 50_000

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
    
from api_keys import open_ai as oai_key, news_database, sec_api_key

def main():
    fullTextSearchApi = FullTextSearchApi(sec_api_key)
    df = pd.DataFrame()
    page = 1
    _filings = True

    while _filings:
        search_parameters = {
            "query": '"target action date"',
            "startDate": datetime.now().strftime("%Y-%m-%d"),
            "endDate": datetime.now().strftime("%Y-%m-%d"),
            "page": page
        }

        response_fulltext = fullTextSearchApi.get_filings(search_parameters)
        if len(response_fulltext['filings']) == 0:
            _filings = False
            break
        
        for filing in response_fulltext['filings']:
            _ = {
                'filedAt': filing['filedAt'],
                'accessionNo': filing['accessionNo'],
                'cik': filing['cik'],            
                'ticker': filing['ticker'],
                'description': filing['description'],
                'type': filing['type'],
                'filingUrl': filing['filingUrl'],
                'formType': filing['formType'],
            }
            df = pd.concat([df, pd.DataFrame([_])], ignore_index=True)
        page += 1

    tad_locations = {i: [] for i in df.index}
    df['tad_loc'] = [[] for _ in range(len(df))]
    tad_logs = {i: tad_locations[i] for i in tad_locations.keys() if len(tad_locations[i]) > 0}


    def occurrences_with_context(text: str, needle: str, window: int = 50):
        out = []
        for m in re.finditer(re.escape(needle), text):
            s, e = m.start(), m.end()
            a = max(0, s - window)
            b = min(len(text), e + window)
            out.append({
                "start": s,
                "end": e,
                "context_start": a,
                "context_end": b,
                "context": text[a:b],
            })
        return out


    queryApi = QueryApi(sec_api_key)
    renderApi = RenderApi(sec_api_key)


    def to_plain_text(markup: str) -> str:
        soup = BeautifulSoup(markup, "lxml")
        for el in soup(["script", "style", "noscript"]):
            el.decompose()
        
        return soup.get_text(separator=" ", strip=True)# separator=" " prevents words/dates being smashed together


    tad_logs = {}
    df = df.reset_index()
    for i, row in tqdm(df.iterrows(), total=len(df)):
        search_params = {
        "query":f"accessionNo: {row.accessionNo} AND ticker: {row.ticker} AND filedAt: {row.filedAt}",
        "sort": [{"filedAt": {"order": "desc"}}],
        }
        response_query = queryApi.get_filings(search_params)
        
        exhibit_documentURLs = []

        for filing in response_query['filings']:
            for document in filing['documentFormatFiles']:
                if 'description' in document.keys():
                    if (document['description'] == 'EXHIBIT 99.1') or (document['description'] == 'EX-99.1') or (document['description'] == 'EX-99') or (document['type'] == 'EXHIBIT 99.1') or (document['type'] == 'EX-99.1'):
                        exhibit_documentURLs.append(document['documentUrl'])
        
        content_filing = [renderApi.get_filing(item['linkToTxt']) for item in response_query['filings'] if item['formType'] == row.formType]
        if len(content_filing) > 1:
            tad_logs[row[0]] = ['Multiple filings found for the same ticker and date']
            # raise ValueError('Multiple filings found for the same ticker and date')
        if len(content_filing) == 0:
            tad_logs[row[0]] = ['No filing found']
            continue
        text_filing = to_plain_text(content_filing[0])
        target_action_date_filing = occurrences_with_context(text_filing, 'target action date', 100)
        
        target_action_date_exhibits = []
        if len(exhibit_documentURLs) > 0:
            exhibit_documentURLs = list(set(exhibit_documentURLs))
            for exhibit_documentURL in exhibit_documentURLs:
                content_exhibit = renderApi.get_filing(exhibit_documentURL)
                
                text_exhibit = to_plain_text(content_exhibit)
                
                target_action_date_exhibits.extend(occurrences_with_context(text_exhibit, 'target action date', 100))
            
        else:
            tad_logs[row[0]] = ['No EXHIBIT 99.1/EX-99.1 found']
        
        df.at[row[0], 'tad_loc'] = target_action_date_exhibits + target_action_date_filing



    def num_tokens_from_string(string: str, encoding_name: str='cl100k_base') -> int:
        """Returns the number of tokens in a text string."""
        encoding = tiktoken.get_encoding(encoding_name)
        num_tokens = len(encoding.encode(string))
        return num_tokens


    total_tokens = 0
    for i, row in df.iterrows():
        for item in row.tad_loc:
            total_tokens += num_tokens_from_string(item['context'])

    if total_tokens > MAX_TOKENS:
        print(f"Total tokens {total_tokens} is greater than MAX_TOKENS {MAX_TOKENS}")
        exit()

    def tad_from_truncated_text(text: list[str]):
        client = OpenAI(api_key=oai_key)

        if len(text) > 1:
            text = '\n'.join(text)

        response = client.responses.create(
            model="gpt-5.2",
            input=f"The following text contains 1 or more dates that are called 'target action dates'. It may contain dates that are not target action dates but are present in the text. The text may also contain incomplete sentences or information. I want you to identify which dates are target action dates. Your response must be the date or dates only and in the format YYYY-MM-DD. The response cannot contain anything but a date in the fomat YYYY-MM-DD, and multiple dates separated by a comma: \n {text}",
            reasoning={
                "effort": "medium"
            },
            text={
                "verbosity": "low"
            }
        )
        return response.output_text

    date_mismatches = []
    df['tad'] = [[] for _ in range(len(df))]
    for i, row in df.iterrows():
        tads = []
        if row.tad_loc:
            for item in row.tad_loc:
                tad_from_ai = tad_from_truncated_text(item['context'])
                tads.append(tad_from_ai)
                
                tad_from_parser = search_dates(item['context'])
                if (len(tad_from_ai) > 0) and (tad_from_parser[0][1].date() != datetime.strptime(tad_from_ai, "%Y-%m-%d").date()):
                    date_mismatches.append((row.ticker, row.filedAt, row.filingUrl, tad_from_parser[0][1].date(), tad_from_ai))
        df.at[i, 'tad'] = tads

    form_types_no_tad = df.loc[df.tad.str.len() == 0].formType.value_counts()

    tad_df = pd.DataFrame()
    for i, row in df.iterrows():
        for item in row.tad:
            if ',' in item:
                tad_df = pd.concat([tad_df, pd.DataFrame({'tad': item.split(',')[0]}, index=[row.ticker])])
                tad_df = pd.concat([tad_df, pd.DataFrame({'tad': item.split(',')[1]}, index=[row.ticker])])
            else:
                tad_df = pd.concat([tad_df, pd.DataFrame({'tad': item}, index=[row.ticker])])
    tad_df = tad_df.reset_index().drop_duplicates().sort_values(by='tad', ascending=False)
    tad_df.rename(columns={'index': 'ticker'}, inplace=True) 

    STOCKS_DB_URL = f"mysql+pymysql://root:{news_database}@127.0.0.1:3306/stocks"


    def save_target_action_dates(
        df: pd.DataFrame,
        *,
        symbol_col: str = "ticker",             
        dt_col: str = "tad",    
        url: str = STOCKS_DB_URL,
        ) -> int:
        engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 5})

        out = df[[symbol_col, dt_col]].copy()
        out["ticker"] = out["ticker"].astype(str).str.slice(0, 5)
        out["tad"] = pd.to_datetime(out["tad"], errors="coerce").dt.date
        out = out.dropna(subset=["ticker", "tad"])
        
        current_df = pd.read_sql_table("target_action_dates", engine)
        out = pd.concat([current_df, out], ignore_index=True)
        out = out.drop_duplicates(subset=["ticker", "tad"])
        
        today = pd.to_datetime(datetime.now().date())
        out["tad"] = pd.to_datetime(out["tad"], errors="coerce")
        out["tad_30days"] = out["tad"].where((out["tad"] > today) & (out["tad"] <= today + pd.Timedelta(days=30)))
        out["tad_5days"]  = out["tad"].where((out["tad"] > today) & (out["tad"] <= today + pd.Timedelta(days=5)))
        

        md = MetaData()
        Table(
            "target_action_dates",
            md,
            Column("ticker", String(5), nullable=False),
            Column("tad", Date, nullable=False),
            Column("tad_30days", Date, nullable=True),
            Column("tad_5days", Date, nullable=True),
            mysql_charset="utf8mb4",
        )
        md.create_all(engine)

        # Append rows
        out.to_sql(
            "target_action_dates",
            con=engine,
            if_exists="replace",
            index=False,
            dtype={"ticker": String(5), "tad": Date(), "tad_30days": Date(), "tad_5days": Date()},
            method="multi",
            chunksize=1000,
        )

        return len(out)

    save_target_action_dates(tad_df)
    
    if len(tad_df) > 0:
        print('Symbols and tads added:\n')
        print([tad_df[['ticker', 'tad']].to_string(index=False)])
        
    else:
        print('No symbols or tads found')

    if len(date_mismatches) > 0:
        print('Date mismatches:\n')
        print("\n".join(
            f"{ticker} filedAt={filedAt} parser={parsed} ai={ai} url={url}"
            for (ticker, filedAt, url, parsed, ai) in date_mismatches
        ))
    else:
        print('No date mismatches found')


if __name__ == "__main__":
    main()
