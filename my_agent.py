import json
import os
import sqlite3
import subprocess
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
from openai import OpenAI

# ==========================================
# 1. Database & Sessions (เหมือนเดิม)
# ==========================================
DB_FILE = "agent_memory.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS chat_sessions (session_id TEXT PRIMARY KEY, user_id TEXT, title TEXT, persona TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (session_id) REFERENCES chat_sessions (session_id))''')
    conn.commit()
    conn.close()

init_db()

def create_or_update_session(session_id, user_id, prompt, persona):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT title FROM chat_sessions WHERE session_id = ?', (session_id,))
    if not cursor.fetchone():
        title = prompt[:30] + "..." if len(prompt) > 30 else prompt
        cursor.execute('INSERT INTO chat_sessions (session_id, user_id, title, persona) VALUES (?, ?, ?, ?)', (session_id, user_id, title, persona))
    conn.commit()
    conn.close()

def save_message(session_id, role, content):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)', (session_id, role, content))
    conn.commit()
    conn.close()

def get_chat_history(session_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT role, content FROM messages WHERE session_id = ? ORDER BY id ASC LIMIT 15', (session_id,))
    rows = cursor.fetchall()
    conn.close()
    return [{"role": r[0], "content": r[1]} for r in rows]

# ==========================================
# 2. ฟังก์ชันเครื่องมือ (Tools) ใหม่เอี่ยม ✨
# ==========================================
def read_local_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f: return f.read()
    except Exception as e: return f"Error: {str(e)}"

def write_local_file(file_path, content):
    try:
        with open(file_path, 'w', encoding='utf-8') as f: f.write(content)
        return f"Success: บันทึกไฟล์ {file_path} เรียบร้อยแล้ว!"
    except Exception as e: return f"Error: {str(e)}"

def list_directory(dir_path="."):
    try:
        files = os.listdir(dir_path)
        return f"Files in '{dir_path}':\n" + "\n".join(files)
    except Exception as e: return f"Error: {str(e)}"

def execute_shell(command):
    try:
        # ⚠️ คำเตือน: ในระบบ Production จริง ควรเช็ค (Whitelist) คำสั่งก่อนรัน
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=15)
        if result.returncode == 0: return f"Output:\n{result.stdout}"
        else: return f"Error Output:\n{result.stderr}"
    except Exception as e: return f"Exception: {str(e)}"

# ฟังก์ชันตัวกลางสำหรับเรียกใช้ Tool
def execute_tool_logic(func_name, args):
    print(f"🛠️ [Tool Called] {func_name} | Args: {args}")
    if func_name == "read_local_file": return read_local_file(args.get("file_path"))
    elif func_name == "write_local_file": return write_local_file(args.get("file_path"), args.get("content"))
    elif func_name == "list_directory": return list_directory(args.get("dir_path", "."))
    elif func_name == "execute_shell": return execute_shell(args.get("command"))
    return f"Error: ไม่พบเครื่องมือ {func_name}"

# ==========================================
# 3. นิยาม JSON Schema สำหรับ AI
# ==========================================
tool_definitions = [
    {"type": "function", "function": {"name": "read_local_file", "description": "อ่านเนื้อหาไฟล์", "parameters": {"type": "object", "properties": {"file_path": {"type": "string"}}, "required": ["file_path"]}}},
    {"type": "function", "function": {"name": "write_local_file", "description": "เขียนหรือแก้ไขไฟล์", "parameters": {"type": "object", "properties": {"file_path": {"type": "string"}, "content": {"type": "string", "description": "เนื้อหาโค้ดที่จะเขียน"}}, "required": ["file_path", "content"]}}},
    {"type": "function", "function": {"name": "list_directory", "description": "ดูรายชื่อไฟล์ในโฟลเดอร์", "parameters": {"type": "object", "properties": {"dir_path": {"type": "string", "description": "พาธของโฟลเดอร์ (ค่าเริ่มต้นคือ .)"}}}}},
    {"type": "function", "function": {"name": "execute_shell", "description": "รันคำสั่ง Terminal/Command Line", "parameters": {"type": "object", "properties": {"command": {"type": "string", "description": "คำสั่งที่จะรัน เช่น ls -la หรือ docker ps"}}, "required": ["command"]}}}
]

# ==========================================
# 4. FastAPI & API Endpoint
# ==========================================
app = FastAPI(title="Claw Code Multi-Tool API")
client = OpenAI(base_url='http://localhost:11434/v1', api_key='ollama')

class ChatRequest(BaseModel):
    session_id: str
    prompt: str
    user_id: Optional[str] = "guest"
    persona: Optional[str] = "developer"

PERSONA_PROMPTS = {
    "developer": "คุณคือ AI Agent ผู้ช่วยเขียนโค้ด คุณสามารถเช็คไฟล์ อ่านไฟล์ และเขียนไฟล์เพื่อแก้บั๊กได้",
    "devops": "คุณคือ System Admin คุณเก่งเรื่องการรันคำสั่ง Terminal เพื่อตรวจสอบระบบและ Docker",
    "general": "คุณคือผู้ช่วย AI ทั่วไป"
}

@app.post("/api/chat")
async def chat_with_agent(request: ChatRequest):
    session_id, user_id, user_prompt, persona_key = request.session_id, request.user_id, request.prompt, request.persona if request.persona in PERSONA_PROMPTS else "developer"
    
    create_or_update_session(session_id, user_id, user_prompt, persona_key)
    save_message(session_id, "user", user_prompt)

    messages = [{"role": "system", "content": PERSONA_PROMPTS[persona_key]}] + get_chat_history(session_id)

    try:
        response = client.chat.completions.create(model="qwen2.5-coder:7b", messages=messages, tools=tool_definitions)
        message = response.choices[0].message
        final_reply = ""

        # จัดการการใช้เครื่องมือ (รองรับทั้งแบบมาตรฐาน และแบบ JSON text bug)
        func_name, args, tool_call_id = None, {}, None

        if message.tool_calls:
            tool_call = message.tool_calls[0]
            func_name, tool_call_id = tool_call.function.name, tool_call.id
            args = json.loads(tool_call.function.arguments)
        elif message.content and '"name":' in message.content and any(t in message.content for t in ["read_local", "write_local", "list_dir", "execute_shell"]):
            try:
                tool_data = json.loads(message.content.replace("```json", "").replace("```", "").strip())
                func_name = tool_data.get("name")
                args = tool_data.get("arguments", {})
                tool_call_id = "manual_json_parse"
            except json.JSONDecodeError:
                pass

        # ถ้ามีการเรียกใช้เครื่องมือ
        if func_name:
            result = execute_tool_logic(func_name, args)
            messages.append({"role": "assistant", "content": message.content} if message.content else message)
            
            # ส่งผลลัพธ์กลับไปให้ AI สรุป
            if tool_call_id == "manual_json_parse":
                messages.append({"role": "user", "content": f"ผลลัพธ์จากเครื่องมือ {func_name}:\n\n{str(result)[:3000]}\n\nจงตอบคำถามโดยใช้ข้อมูลนี้"})
            else:
                messages.append({"role": "tool", "tool_call_id": tool_call_id, "name": func_name, "content": str(result)[:3000]})

            final_response = client.chat.completions.create(model="qwen2.5-coder:7b", messages=messages)
            final_reply = final_response.choices[0].message.content
        else:
            final_reply = message.content

        save_message(session_id, "assistant", final_reply)
        return {"reply": final_reply, "tool_used": func_name}

    except Exception as e:
        print(f"[Error] {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))