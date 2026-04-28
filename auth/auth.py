import os
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext
from jose import JWTError, jwt
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from dotenv import load_dotenv
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from db.db_resiliencia import db

load_dotenv()

# Configurações de E-mail
SMTP_SERVER = "smtp.office365.com" 
SMTP_PORT = 587
SMTP_USER = "tecnologia2@scryta.com.br"
SMTP_PASS = os.getenv("SMTP_PASSWORD") 

router = APIRouter(
    prefix="/auth",
    tags=["auth"]
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("⚠️  SECRET_KEY não definida no arquivo .env")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 300

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    full_name: Optional[str] = None

class Token(BaseModel):
    access_token: str
    token_type: str


def verificar_usuario_existente(username: str, email: str):
    if db.get_user_by_username(username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuário já existe."
        )
    if db.get_user_by_email(email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="E-mail já cadastrado."
        )


@router.post("/signup", response_model=dict, summary="Criar novo usuário")
def signup(user: UserCreate):
    if db.get_user_by_email(user.email):
        raise HTTPException(status_code=400, detail="E-mail já cadastrado.")
    
    hashed_password = pwd_context.hash(user.password)

    try:
        user_id = db.insert_user(
            username=user.email,
            email=user.email, 
            full_name=user.full_name, 
            hashed_password=hashed_password
        )
        return {
            "mensagem": "Usuário registrado com sucesso",
            "user_id": user_id
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro no banco: {str(e)}")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def authenticate_user(email_as_username: str, password: str):
    user_doc = db.get_user_by_email(email_as_username)

    if not user_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Este e-mail ainda não possui cadastro. Crie sua conta para acessar o sistema."
        )

    if not verify_password(password, user_doc["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário ou senha incorretos",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user_doc


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


@router.post("/token", response_model=Token, summary="Obter token (login)")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["username"]},
        expires_delta=access_token_expires
    )

    return {"access_token": access_token, "token_type": "bearer"}


async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Não autenticado",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user_doc = db.get_user_by_username(username)
    if user_doc is None:
        raise credentials_exception
    return user_doc


@router.post("/forgot-password", summary="Enviar link de recuperação via SMTP")
async def forgot_password(payload: dict):
    email = payload.get("email")
    user = db.get_user_by_email(email)
    
    if not user:
        raise HTTPException(
            status_code=404,
            detail="Este e-mail não possui cadastro. Crie sua conta antes de solicitar a recuperação de senha."
        )

    token = create_access_token(data={"sub": user["username"]}, expires_delta=timedelta(minutes=15))
    reset_link = f"http://localhost:5173/reset-password?token={token}"

    msg = MIMEMultipart('alternative') 
    msg['From'] = SMTP_USER
    msg['To'] = email
    msg['Subject'] = "Recuperação de Senha - SISTEMA TRIAGEM"
    
    nome_usuario = user.get('full_name', 'Usuário')

    text_body = f"Olá {nome_usuario},\n\nVocê solicitou a redefinição de sua senha.\nCopie e cole este link no seu navegador para criar uma nova senha:\n\n{reset_link}"
    
    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; background-color: #f3f4f6; padding: 30px; margin: 0;">
        <div style="max-width: 500px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 10px rgba(0,0,0,0.05); border: 1px solid #e5e7eb;">
            <div style="background-color: #18181b; padding: 25px; text-align: center; border-bottom: 5px solid #6366f1;">
                <h2 style="color: #ffffff; margin: 0; font-size: 24px; letter-spacing: 1px;">SISTEMA TRIAGEM</h2>
            </div>
            <div style="padding: 40px 30px; text-align: center;">
                <p style="color: #4b5563; font-size: 16px; margin-bottom: 10px;">Olá, <strong>{nome_usuario}</strong>!</p>
                <p style="color: #6b7280; font-size: 14px; margin-bottom: 30px; line-height: 1.5;">Recebemos um pedido para redefinir a senha da sua conta corporativa. Clique no botão abaixo para criar uma nova senha.</p>
                
                <a href="{reset_link}" style="display: inline-block; background-color: #6366f1; color: #ffffff; text-decoration: none; padding: 14px 32px; border-radius: 8px; font-weight: bold; font-size: 14px; text-transform: uppercase; letter-spacing: 1px;">Redefinir Senha</a>
                
                <p style="color: #9ca3af; font-size: 12px; margin-top: 35px; border-top: 1px solid #f3f4f6; padding-top: 15px;">Se você não solicitou esta alteração, ignore este e-mail. O link expira em 15 minutos.</p>
            </div>
        </div>
    </body>
    </html>
    """

    part1 = MIMEText(text_body, 'plain')
    part2 = MIMEText(html_body, 'html')
    msg.attach(part1)
    msg.attach(part2)

    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg, from_addr=SMTP_USER, to_addrs=[email])
        server.quit()
        return {"mensagem": "E-mail enviado com sucesso."}
    except Exception as e:
        print(f"Detalhe do erro SMTP: {str(e)}") 
        raise HTTPException(status_code=500, detail=f"Erro ao enviar e-mail: {str(e)}")


@router.get("/me", summary="Obter dados do usuário logado")
async def get_me(current_user=Depends(get_current_user)):
    return {
        "username": current_user["username"],
        "email": current_user["email"],
        "full_name": current_user.get("full_name")
    }


class PasswordReset(BaseModel):
    token: str
    new_password: str

@router.post("/reset-password", summary="Redefinir senha com token")
async def reset_password(payload: PasswordReset):
    try:
        decoded = jwt.decode(payload.token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = decoded.get("sub")
        if not username:
            raise HTTPException(status_code=400, detail="Token inválido.")
    except JWTError:
        raise HTTPException(status_code=400, detail="Link expirado ou inválido. Peça um novo e-mail.")

    user = db.get_user_by_username(username)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")

    hashed_password = pwd_context.hash(payload.new_password)
    db.update_password(username, hashed_password)

    return {"mensagem": "Senha redefinida com sucesso."}
