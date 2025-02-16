# **Networking and Distributed Systems Labs**  

### **About the Project**  
This is a collaborative project for implementing and documenting **labs for the course "Network System Software and Distributed Systems."** The goal is to create structured and practical solutions for each lab, following modern networking and system programming principles.  

### **Project Structure**   
📂 `docs/` – Includes PDF with lab assignments.  
📂 `server/` – Code for the networking server.  
📂 `client/` – Code for the client-side applications.  

### **Technologies Used**  
- **Python** (Networking & System Programming)  
- **Sockets & TCP/IP**
- **Rich library** (For better terminal UI)  
- **UV package manager** (For managing dependencies)  

### **Setup & Installation**  
Make sure you have **UV** installed. If not, install it:  
```bash  
pip install uv  
```
Then, install all project dependencies with UV:

```bash
uv sync  
```

### How to Run
1. Clone the repository:
```bash
git clone https://github.com/fozboom/Network-Programming.git  
cd Network-Programming
```
2. Run the **Server** using **UV**:

```bash
uv run python server/main.py  
```

3. Run the **Client**:
```bash
uv run python client/main.py  
```

### Team
**Server Developer**: https://github.com/fozboom

**Client Developer**: https://github.com/birmay95

## License

This project is for educational purposes only.




