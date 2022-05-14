# import datetime
# from typing import Optional
# from pydantic import EmailStr

# from redis_om import HashModel


# class User(HashModel):
#     """ user info profile """
#     first_name: str
#     telegram_id: int
#     last_name: str
#     join_date: datetime.date
#     age: int
#     bio: Optional[str]

# user = id , first_name , last_name , join_date , age , bio
