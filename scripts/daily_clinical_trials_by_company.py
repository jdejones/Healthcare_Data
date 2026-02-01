import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
    
from clinical_trials import clinical_trials_by_company_update_storage

if __name__ == "__main__":
    clinical_trials_by_company_update_storage()