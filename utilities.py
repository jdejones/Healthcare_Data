import json
import re

#Make watchlist for specific symbols
def make_watchlist(file_path: str) -> list[str]:
    with open(file_path, 'r') as f:
        return [line.strip() for line in f.readlines()]
all_symbols = "E:\Market Research\Studies\Sector Studies\Watchlists\\all_symbols.txt"
all_symbols = make_watchlist(all_symbols)

#Load sectors and industries
sectors_industries = json.load(open(r"E:\Market Research\Dataset\Fundamental Data\symbol_sector_industry.txt"))
company_names = json.load(open(r"E:\Market Research\Dataset\Fundamental Data\company_names.txt"))

# Process healthcare company names for clinicaltrials.gov search.
healthcare_companies = {k:v for k,v in company_names.items() if (k in sectors_industries) and (sectors_industries[k]['sector'] == 'Healthcare')}
def clean_company_names(company_names: dict[str, str]) -> dict[str, str]:
    company_names_cleaned = {}
    #I haven't tested removal of some of these suffixes; such as 'LABORATORIES' or 'SERVICES'.
    suffixes = {' CO', ' AG', ' A', ' CORP', ' GROUP', ' INC', ' LABORATORIES', ' LTD', ' NV', ' PLC', ' S', ' SA', ' SE', ' SERVICES', ' SPA'}
    for k,v in company_names.items():
        for suffix in suffixes:
            if re.search(suffix + '$', v):
                company_names_cleaned[k] = v.replace(suffix, '')
                break
    return company_names_cleaned
healthcare_companies_cleaned = clean_company_names(healthcare_companies)

