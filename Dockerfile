# ใช้ Python เวอร์ชัน 3.11 แบบ slim เพื่อให้ Image มีขนาดเล็ก
FROM python:3.11-slim

# ตั้งค่า Working Directory ภายใน Container
WORKDIR /app

# คัดลอกไฟล์ทั้งหมดจากโฟลเดอร์ปัจจุบันเข้าไปใน /app ของ Container
COPY . /app

# หากโปรเจกต์มีการเพิ่มไฟล์ requirements.txt ในอนาคต สามารถลบเครื่องหมาย # ออกได้
# RUN pip install --no-cache-dir -r requirements.txt

# ตั้งค่า Entrypoint ให้ชี้ไปที่สคริปต์หลักของโปรเจกต์
ENTRYPOINT ["python3", "-m", "src.main"]

# ตั้งค่า Default Command (หากไม่ได้ระบุคำสั่งตอนรัน จะใช้คำสั่ง summary)
CMD ["summary"]