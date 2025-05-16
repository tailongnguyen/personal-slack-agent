import requests
import re
import logging
from typing import List
from agents import function_tool
from datetime import datetime, timedelta

@function_tool
def ft_summation_tool(array: List[int]) -> int:
    """Perform the summation."""
    logging.info("[Tool] summation_tool({})".format(array))
    return sum(array)

def summation_tool(array: List[int]) -> int:
    if not isinstance(array, list):
        raise ValueError("Input must be a list")
    if not all(isinstance(i, int) for i in array):
        raise ValueError("All elements in the list must be integers")
    return sum(array)

@function_tool
def ft_get_today_date() -> str:
    """Returns today's date in YYYY-MM-DD format."""
    logging.info("[Tool] get_today_date()")
    return get_today_date()

def get_today_date() -> str:
    return datetime.now().strftime('%Y-%m-%d')

@function_tool
def ft_get_request_report(from_date: str, to_date: str) -> dict:    
    '''
    Fetch request report from the API.
    Args:
        from_date (str): The start date in YYYY-MM-DD format.
        to_date (str): The end date in YYYY-MM-DD format.
    Returns:
        dict: The response from the API.
    '''
    logging.info("[Tool] get_request_report({}, {})".format(from_date, to_date))
    return get_request_report(from_date, to_date)

def get_request_report(from_date, to_date):
    if not from_date or not to_date:
        return {"error": "from_date and to_date are required"}
    if from_date > to_date:
        return {"error": "from_date must be less than to_date"}
    if not isinstance(from_date, str) or not isinstance(to_date, str):
        return {"error": "from_date and to_date must be strings in YYYY-MM-DD format"}
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", from_date) or not re.match(r"^\d{4}-\d{2}-\d{2}$", to_date):
        return {"error": "from_date and to_date must be in YYYY-MM-DD format"}
    
    if from_date == to_date:
        from_date_obj = datetime.strptime(from_date, "%Y-%m-%d")
        to_date_obj = from_date_obj + timedelta(days=1)
        to_date = to_date_obj.strftime("%Y-%m-%d")
        
    url = f"https://ekyc-api.kalapa.vn/api/data/get-report?from_date={from_date}&to_date={to_date}"

    headers = {
    'Authorization': '5bb42ea331ee010001a0b7d7zl0l6t0k3ra85656887lrn17713q775g'
    }

    response = requests.request("GET", url, headers=headers)

    if response.status_code != 200:
        return {"error": f"{response.status_code} - {response.text}"}
    
    return response.json()
