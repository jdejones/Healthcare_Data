import requests
import time
from utilities import healthcare_companies_cleaned
from tqdm import tqdm
import pandas as pd
import json
from sqlalchemy import create_engine
from sqlalchemy.types import String, DateTime, JSON, String, Boolean
from api_keys import news_database
import re
from flashtext import KeywordProcessor
from rapidfuzz import process, fuzz





def clinical_trials_by_company_initial_storage(start_date: str):
    companies_lst = list(healthcare_companies_cleaned.keys())
    BATCH_SIZE = 100
    companies_str = ''
    start_date = f'AREA%5BLastUpdatePostDate%5DRANGE%5B{start_date}%2CMAX%5D'
    results = []

    for i in tqdm(range(300, len(companies_lst), BATCH_SIZE), desc="Import From ClinicalTrials.gov"):
        batch = companies_lst[i:i+BATCH_SIZE]
        for company in batch:
            if company != batch[-1]:
                companies_str += f"COVERAGE%5BContains%5D{healthcare_companies_cleaned[company]}%20OR%20"
            else:
                companies_str += f"COVERAGE%5BContains%5D{healthcare_companies_cleaned[company]}"


        response = requests.get(f"https://clinicaltrials.gov/api/v2/studies?format=json&query.term={start_date}&pageSize=1000&query.spons={companies_str}&sort=LastUpdatePostDate")
        _response = response.json()
        results.append(_response)

        if ('nextPageToken' in _response.keys()) and (_response['nextPageToken']):
            while _response['nextPageToken']:
                response = requests.get(f"https://clinicaltrials.gov/api/v2/studies?format=json&query.term={start_date}&pageSize=1000&query.spons={companies_str}&sort=LastUpdatePostDate&pageToken={_response['nextPageToken']}")
                _response = response.json()
                results.append(_response)
                if 'nextPageToken' not in _response.keys():
                    break
                time.sleep(10)
        companies_str = ''
        

    def get_in(obj, path, default=None):
        """Safely walk nested dict keys."""
        cur = obj
        for key in path:
            if isinstance(cur, dict) and key in cur:
                cur = cur[key]
            else:
                return default
        return cur

    df = pd.DataFrame()
    for results in tqdm(results, desc="Constructing DataFrame"):
        for study in results['studies']:
            # Values (from the JSON paths listed in the In[52] cell)
            study_start_date = get_in(study, ['protocolSection', 'statusModule', 'startDateStruct', 'date'])
            study_start_type = get_in(study, ['protocolSection', 'statusModule', 'startDateStruct', 'type'])
            primary_completion_date = get_in(study, ['protocolSection', 'statusModule', 'primaryCompletionDateStruct', 'date'])
            primary_completion_type = get_in(study, ['protocolSection', 'statusModule', 'primaryCompletionDateStruct', 'type'])
            study_completion_date = get_in(study, ['protocolSection', 'statusModule', 'completionDateStruct', 'date'])
            study_completion_type = get_in(study, ['protocolSection', 'statusModule', 'completionDateStruct', 'type'])
            first_submitted = get_in(study, ['protocolSection', 'statusModule', 'studyFirstSubmitDate'])
            first_submitted_that_met_QC_Criteria = get_in(study, ['protocolSection', 'statusModule', 'studyFirstSubmitQcDate'])
            first_posted = get_in(study, ['protocolSection', 'statusModule', 'studyFirstPostDateStruct', 'date'])
            last_update_submitted_that_Met_QC_Criteria = get_in(study, ['protocolSection', 'statusModule', 'lastUpdateSubmitDate'])
            last_update_posted_date = get_in(study, ['protocolSection', 'statusModule', 'lastUpdatePostDateStruct', 'date'])
            last_update_posted_type = get_in(study, ['protocolSection', 'statusModule', 'lastUpdatePostDateStruct', 'type'])
            last_verified = get_in(study, ['protocolSection', 'statusModule', 'statusVerifiedDate'])

            phase = get_in(study, ['protocolSection', 'designModule', 'phases'])
            conditions = get_in(study, ['protocolSection', 'conditionsModule', 'conditions'])
            intervention_treatment = get_in(study, ['protocolSection', 'armsInterventionsModule', 'interventions'])
            sponsor_collaborators_investigators = get_in(study, ['protocolSection', 'identificationModule', 'organization', 'fullName'])
            keywords_provided_by = get_in(study, ['protocolSection', 'conditionsModule', 'keywords'])
            studies_a_us_fda_regulated_device_product = get_in(study, ['protocolSection', 'oversightModule', 'isFdaRegulatedDevice'])
            studies_a_us_fda_regulated_drug_product = get_in(study, ['protocolSection', 'oversightModule', 'isFdaRegulatedDrug'])

            condition_browse_mesh_terms = get_in(study, ['derivedSection', 'conditionBrowseModule', 'meshes'])
            condition_browse_ancestor_terms = get_in(study, ['derivedSection', 'conditionBrowseModule', 'ancestors'])
            intervention_browse_mesh_terms = get_in(study, ['derivedSection', 'interventionBrowseModule', 'meshes'])

            # IMPORTANT: build as a 1-row record (prevents "All arrays must be of the same length")
            _df = pd.DataFrame([
                {
                    'Study_Start_Date': study_start_date,
                    'Study_Start_Type': study_start_type,
                    'Primary_Completion_Date': primary_completion_date,
                    'Primary_Completion_Type': primary_completion_type,
                    'Study_Completion_Date': study_completion_date,
                    'Study_Completion_Type': study_completion_type,
                    'First_Submitted': first_submitted,
                    'First_Submitted_that_met_QC_Criteria': first_submitted_that_met_QC_Criteria,
                    'First_Posted': first_posted,
                    'Last_Update_Submitted_that_Met_QC_Criteria': last_update_submitted_that_Met_QC_Criteria,
                    'Last_Update_Posted_Date': last_update_posted_date,
                    'Last_Update_Posted_Type': last_update_posted_type,
                    'Last_Verified': last_verified,
                    'Phase': phase,
                    'Conditions': conditions,
                    'Intervention_Treatment': intervention_treatment,
                    'Sponsor_Collaborators_Investigators': sponsor_collaborators_investigators,
                    'Keywords_Provided_by': keywords_provided_by,
                    'Studies_a_US_FDA_Reuglated_Device_Product': studies_a_us_fda_regulated_device_product,
                    'Studies_a_US_FDA_Regulated_Drug_Product': studies_a_us_fda_regulated_drug_product,
                    'Condition_Browse_MeSH_Terms': condition_browse_mesh_terms,
                    'Condition_Browse_Ancestor_Terms': condition_browse_ancestor_terms,
                    'Intervention_Browse_MeSH_Terms': intervention_browse_mesh_terms,
                }
            ])
            
            df = pd.concat([df, _df])


    database_url = f"mysql+pymysql://root:{news_database}@127.0.0.1:3306/healthcare"
    engine = create_engine(
        database_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 5},
    )

    _df = df.copy()

    healthcare_companies_cleaned_inverted = {v:k for k,v in healthcare_companies_cleaned.items()}


    CORP_SUFFIXES = r"""
    \b(inc|incorporated|corp|corporation|co|company|ltd|limited|llc|plc|sa|ag|nv|group|holdings|holding)\b
    """

    def normalize(s: str) -> str:
        if pd.isna(s):
            return ""
        s = str(s).lower()
        s = s.replace("&", " and ")
        s = re.sub(r"[^\w\s]", " ", s)                 # drop punctuation
        s = re.sub(CORP_SUFFIXES, " ", s, flags=re.X)  # remove common suffixes
        s = re.sub(r"\s+", " ", s).strip()
        return s


    def build_keyword_processor(name_to_ticker: dict):
        kp = KeywordProcessor(case_sensitive=False)
        for name, ticker in name_to_ticker.items():
            key = normalize(name)
            if key:
                kp.add_keyword(key, ticker)  # maps normalized company name -> ticker
        return kp

    def stage_a_assign(df, text_col, name_to_ticker):
        kp = build_keyword_processor(name_to_ticker)

        norm_col = df[text_col].map(normalize)
        # FlashText expects the same normalization; we search on normalized text.
        hits = norm_col.map(lambda s: kp.extract_keywords(s))  # list of tickers found

        # If multiple companies are mentioned, pick the first; or keep the list.
        df = df.copy()
        df["ticker_stage_a"] = hits.map(lambda xs: xs[0] if xs else pd.NA)
        df["_norm_text"] = norm_col
        return df


    def stage_b_assign(df, name_to_ticker, threshold=92):
        # Build choices from normalized company names
        choices = []
        ticker_by_choice = {}
        for name, ticker in name_to_ticker.items():
            c = normalize(name)
            if not c:
                continue
            # Optional guard: skip very short single-token names (reduce false positives)
            if len(c) < 4 and " " not in c:
                continue
            choices.append(c)
            ticker_by_choice[c] = ticker

        def best_ticker(norm_text):
            if not norm_text:
                return pd.NA
            match = process.extractOne(
                norm_text,
                choices,
                scorer=fuzz.token_set_ratio,  # good for word reordering / extra words
            )
            if match is None:
                return pd.NA
            choice, score, _idx = match
            return ticker_by_choice[choice] if score >= threshold else pd.NA

        df = df.copy()
        needs = df["ticker_stage_a"].isna()
        df.loc[needs, "ticker_stage_b"] = df.loc[needs, "_norm_text"].map(best_ticker)

        # final ticker: prefer stage A, else stage B
        df["ticker"] = df["ticker_stage_a"].combine_first(df["ticker_stage_b"])
        return df

    _df = stage_a_assign(_df, text_col="Sponsor_Collaborators_Investigators", name_to_ticker=healthcare_companies_cleaned_inverted)
    _df = stage_b_assign(_df, healthcare_companies_cleaned_inverted, threshold=92)

    # df2["ticker"] now filled where a match was found





    # 1) Ensure datetimes are real datetimes (not strings)
    date_cols = ["Study_Start_Date", "Primary_Completion_Date", "Study_Completion_Date", 
                "First_Submitted", "First_Submitted_that_met_QC_Criteria", "First_Posted", 
                "Last_Update_Submitted_that_Met_QC_Criteria", "Last_Update_Posted_Date", "Last_Verified"]  # <-- your date columns
    for c in date_cols:
        _df[c] = pd.to_datetime(_df[c], errors="coerce")

    # 2) Convert complex object columns (list/dict/json-like) to JSON (or TEXT)
    complex_cols = ['Phase', 'Conditions',
        'Intervention_Treatment', 'Sponsor_Collaborators_Investigators',
        'Keywords_Provided_by', 'Condition_Browse_MeSH_Terms',
        'Condition_Browse_Ancestor_Terms', 'Intervention_Browse_MeSH_Terms']  # <-- your complex columns

    def to_json_or_none(x):
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return None
        if isinstance(x, (dict, list)):
            return json.dumps(x, ensure_ascii=False)
        # if it's already a JSON string, keep it; otherwise serialize as a string
        return x if isinstance(x, str) else json.dumps(x, ensure_ascii=False, default=str)

    for c in complex_cols:
        _df[c] = _df[c].map(to_json_or_none)

    # 3) Optional: normalize NaN -> None for SQL NULLs
    _df = _df.where(pd.notnull(_df), None)


    bool_cols = ['Studies_a_US_FDA_Reuglated_Device_Product', 'Studies_a_US_FDA_Regulated_Drug_Product']  # <-- your boolean columns

    def to_bool_or_none(x):
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return None
        if isinstance(x, bool):
            return x
        if isinstance(x, (int, float)) and x in (0, 1):
            return bool(int(x))
        if isinstance(x, str):
            v = x.strip().lower()
            if v in ("true", "t", "yes", "y", "1"):
                return True
            if v in ("false", "f", "no", "n", "0"):
                return False
        return None  # or raise if you want strictness

    for c in bool_cols:
        _df[c] = _df[c].map(to_bool_or_none)


    str_cols = ['Study_Start_Type', 'Primary_Completion_Type', 'Study_Completion_Type', 'Last_Update_Posted_Type']  # <-- your string columns

    for c in str_cols:
        # If the column might contain non-strings, normalize to string first (preserving NULLs)
        df[c] = df[c].astype("string")            # pandas StringDtype supports <NA>
        df[c] = df[c].str.strip()                 # trim leading/trailing whitespace
        df[c] = df[c].replace({"": pd.NA})        # empty -> NA (later becomes SQL NULL)


    # 4) Choose SQL column types (important for object/JSON columns)
    # If your MySQL version supports JSON, prefer JSON; otherwise use Text.
    dtype_map = {
        "Study_Start_Date": DateTime(),
        "Primary_Completion_Date": DateTime(),
        "Study_Completion_Date": DateTime(),
        "First_Submitted": DateTime(),
        "First_Submitted_that_met_QC_Criteria": DateTime(),
        "First_Posted": DateTime(),
        "Last_Update_Submitted_that_Met_QC_Criteria": DateTime(),
        "Last_Update_Posted_Date": DateTime(),
        "Last_Verified": DateTime(),
        'Phase': JSON(), 
        'Conditions': JSON(),
        'Intervention_Treatment': JSON(), 
        'Sponsor_Collaborators_Investigators': JSON(),
        'Keywords_Provided_by': JSON(), 
        'Condition_Browse_MeSH_Terms': JSON(),
        'Condition_Browse_Ancestor_Terms': JSON(), 
        'Intervention_Browse_MeSH_Terms': JSON(),
        'Studies_a_US_FDA_Reuglated_Device_Product': Boolean(),
        'Studies_a_US_FDA_Regulated_Drug_Product': Boolean(),
        'Study_Start_Type': String(10),
        'Primary_Completion_Type': String(10),
        'Study_Completion_Type': String(10),
        'Last_Update_Posted_Type': String(10)
    }

    # 5) Write using chunks (30MB is fine, but chunking avoids giant INSERTs)
    table_name = "clinical_trials_by_company"

    with engine.begin() as conn:  # transaction
        _df.to_sql(
            name=table_name,
            con=conn,
            if_exists="append",       # "fail" | "replace" | "append"
            index=False,
            chunksize=1000,           # tune 500–5000 depending on row width
            method="multi",           # batches INSERTs (usually faster)
            dtype=dtype_map,          # optional but recommended
        )