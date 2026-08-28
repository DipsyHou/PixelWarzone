from pydantic import BaseModel
from typing import Optional, List


class RegisterRequest(BaseModel):
    username: str
    password: str
    email: str


class LoginRequest(BaseModel):
    username: str
    password: str


class CreateRoomRequest(BaseModel):
    room_name: str
    max_players: int = 8
    password: Optional[str] = None


class JoinRoomRequest(BaseModel):
    room_id: Optional[str] = None
    password: Optional[str] = None


class AdminRequest(BaseModel):
    admin_password: str


class UpdateLoadoutRequest(BaseModel):
    weapon_slots: List[str]
    perks: List[str]
