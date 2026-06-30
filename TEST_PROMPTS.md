# 🧪 Nexus Brain Bot - 15+ Test Prompts

Test all features of @nexus_brain_devs_bot with these curated prompts.

---

## 📋 Test Prompts by Feature

### 1️⃣ **Basic Greeting** (Tests input routing)
```
Hello bot, what can you do?
```
Expected: Bot introduces itself and capabilities

### 2️⃣ **Memory Storage - Save Information** (Tests memory writer)
```
Remember: My name is Samet and I work as a Software Engineer
```
Expected: Bot acknowledges and stores the information

### 3️⃣ **Memory Retrieval - Ask About Stored Info** (Tests memory retriever + search)
```
What do you know about me?
```
Expected: Bot retrieves and tells you the information it stored earlier

### 4️⃣ **Multi-turn Conversation** (Tests conversation history)
```
I'm learning machine learning right now
```
Then follow up with:
```
What should I learn next based on that?
```
Expected: Bot remembers context from previous message

### 5️⃣ **Complex Question Requiring Reasoning** (Tests reasoner node)
```
Explain the difference between supervised and unsupervised learning
```
Expected: Detailed multi-step answer with reasoning

### 6️⃣ **Save Learning Information** (Tests memory storage)
```
Remember: I prefer Python over JavaScript for machine learning
```
Expected: Stores language preference

### 7️⃣ **Retrieval of Learning Info** (Tests hybrid search - vector + keyword)
```
What programming languages do I prefer?
```
Expected: Bot recalls stored preference

### 8️⃣ **PII Detection Test** (Tests PII masking)
```
My email is samet@example.com and my phone is +1-555-123-4567
```
Expected: Bot detects and masks personal information

### 9️⃣ **Entity Extraction Test** (Tests entity extractor)
```
I work at Google in Mountain View and my manager is John Smith
```
Expected: Bot identifies entities (company, location, person name)

### 🔟 **Technical Question** (Tests LLM reasoning)
```
How do neural networks learn through backpropagation?
```
Expected: Technical explanation with multi-step reasoning

### 1️⃣1️⃣ **Question About Earlier Memory** (Tests search with context)
```
You remember when I told you about my job?
```
Expected: Bot recalls previously stored information

### 1️⃣2️⃣ **Follow-up Question** (Tests conversation threading)
```
Tell me more about that
```
Expected: Bot understands "that" refers to previous topic

### 1️⃣3️⃣ **Multiple Pieces of Information** (Tests memory storage at scale)
```
Remember all of this:
- I love Python programming
- I'm interested in AI and machine learning
- I work remotely
- I like to learn new technologies
```
Expected: Bot stores all pieces of information

### 1️⃣4️⃣ **Search Test - Semantic Similarity** (Tests vector search)
```
What are my interests?
```
Expected: Bot retrieves information you stored earlier using semantic understanding

### 1️⃣5️⃣ **Reasoning With Multiple Sources** (Tests hybrid reasoning)
```
Based on what you know about me, what AI projects should I work on?
```
Expected: Bot uses stored information + reasoning to suggest projects

### 1️⃣6️⃣ **Clear/Reset Test** (Tests state management)
```
Forget everything about me and start fresh
```
Expected: Bot acknowledges (Note: actual data remains in DB for audit trail)

### 1️⃣7️⃣ **Long Context Test** (Tests token management)
```
Tell me everything you know about me in detail
```
Expected: Bot summarizes all stored information

### 1️⃣8️⃣ **Multiple PII Types** (Tests comprehensive PII detection)
```
Contact me at john.doe@company.com or 123-456-7890, my credit card is 4532-1111-2222-3333
```
Expected: Bot detects email, phone, and credit card (masked)

### 1️⃣9️⃣ **Complex Multi-step Reasoning** (Tests reasoner)
```
I know Python, JavaScript, and SQL. Given I want to learn machine learning, 
what's the best order to learn: TensorFlow, PyTorch, Scikit-learn?
```
Expected: Bot reasons through options considering prerequisites

### 2️⃣0️⃣ **Chitchat** (Tests greeting classifier)
```
How are you doing today?
```
Expected: Friendly response

---

## 📊 Feature Coverage Matrix

| Feature | Test Prompt | Expected Behavior |
|---------|-------------|-------------------|
| **Input Router** | #1, #20 | Classifies greeting vs query vs memory |
| **Memory Retriever** | #3, #7, #11 | Searches and retrieves stored info |
| **Entity Extractor** | #8, #9, #18 | Detects entities and PII |
| **Reasoner** | #5, #10, #15, #19 | Multi-step logical reasoning |
| **Response Generator** | All | Generates contextual responses |
| **Memory Writer** | #2, #6, #13 | Stores information in database |
| **PII Detection** | #8, #18 | Masks sensitive information |
| **Hybrid Search** | #14 | Vector + keyword search |
| **Context Awareness** | #4, #12, #17 | Remembers conversation history |
| **Semantic Understanding** | #11, #15, #19 | Understands meaning not just keywords |

---

## ✅ Success Criteria

For each prompt, you should see:

1. **Response appears in Telegram** (within 2-4 seconds)
2. **Response is relevant** to your question
3. **Information is personalized** (if you stored info earlier)
4. **No errors in logs** (`docker logs nexus-celery -f`)
5. **Data persists** across multiple conversations

---

## 📈 Performance Metrics to Watch

While testing, monitor these in logs:

```
✅ [Celery] Message processed: 
   - type=greeting (message classification)
   - tokens=XXX (LLM token usage)
   - latency=XXXMS (response time)
   - stored=True/False (memory saved)

📤 [Telegram] Response sent (message delivered)
```

**Expected latency:** 2-4 seconds (includes LLM API calls)

---

## 🎯 Testing Strategy

### Basic Flow (5 minutes)
1. Send #1 (Greeting)
2. Send #2 (Store info)
3. Send #3 (Retrieve info)
4. Send #14 (Search for info)
5. Send #20 (Chitchat)

### Comprehensive Flow (15 minutes)
1. Follow Basic Flow
2. Test all #1-#20 in order
3. Watch logs for errors
4. Check data persistence

### Stress Test (30 minutes)
1. Send all prompts multiple times
2. Vary the order
3. Add custom variations
4. Monitor performance degradation

---

## 💡 Pro Tips

- **Vary wording:** Use different ways to ask similar things (tests semantic understanding)
- **Mix stored info:** Reference information you stored in earlier prompts
- **Add custom info:** Create your own prompts based on the patterns
- **Check logs:** `docker logs nexus-celery -f` shows what the bot is doing
- **Export conversation:** All messages are saved in the database for analysis

