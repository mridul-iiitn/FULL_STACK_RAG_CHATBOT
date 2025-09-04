import { useState, useEffect, useRef } from "react";
import axios from "axios";
import ReactMarkdown from 'react-markdown';
// Naye icons (Sun/Moon for theme toggle)
import { FiSend, FiUpload, FiLoader, FiSun, FiMoon } from 'react-icons/fi';

// Bot ke liye ek cute SVG avatar
const BotAvatar = () => (
  <div className="w-10 h-10 rounded-full bg-indigo-500 flex items-center justify-center flex-shrink-0">
    <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
  </div>
);

// User ke liye avatar
const UserAvatar = () => (
    <div className="w-10 h-10 rounded-full bg-gray-600 dark:bg-gray-700 flex items-center justify-center flex-shrink-0">
         <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" /></svg>
    </div>
);

function App() {
  const [file, setFile] = useState(null);
  const [messages, setMessages] = useState([
    {
      sender: "bot",
      text: "Namaste! Main aapka Sarkari Yojana Sahayak hoon. Kripya yojana se sambandhit PDF document upload karein aur apne sawaal poochein.",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState("Ready");
  const [theme, setTheme] = useState('dark');
  const chatEndRef = useRef(null);

  const toggleTheme = () => {
    setTheme(prevTheme => (prevTheme === 'dark' ? 'light' : 'dark'));
  };
  
  // Is useEffect se hum poore page par theme class lagate hain
  useEffect(() => {
    const root = window.document.documentElement;
    root.classList.remove('light', 'dark');
    root.classList.add(theme);
  }, [theme]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);
  
  const suggestedQuestions = [
    "Is yojana ke liye kaun patra hai?",
    "Aavedan karne ke liye kya documents chahiye?",
    "Is yojana ke mukhya laabh kya hain?",
    "Yojana ka aavedan kaise karein?",
  ];

  const handleFileChange = (e) => setFile(e.target.files[0]);

  const handleUpload = async () => {
    if (!file) return;
    const formData = new FormData();
    formData.append("file", file);
    setLoading(true);
    setStatus("Processing document...");
    try {
      const res = await axios.post("http://localhost:5000/upload", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setStatus(`Success! Document processed with ${res.data.chunks_added} chunks.`);
      setFile(null);
    } catch (err) {
      console.error(err);
      setStatus("Upload failed. See console.");
    } finally {
      setLoading(false);
    }
  };

  const handleSend = async (question = input) => {
    if (!question.trim()) return;
    const userMessage = { sender: "user", text: question };
    setMessages((prev) => [...prev, userMessage]);
    if (input) setInput("");
    setLoading(true);
    setStatus("Finding answer...");
    try {
      const res = await axios.post("http://localhost:5000/query", { question });
      const botMessage = { sender: "bot", text: res.data.answer, sources: res.data.sources };
      setMessages((prev) => [...prev, botMessage]);
      setStatus("Ready");
    } catch (err) {
      console.error(err);
      setStatus("Error. See console.");
      const botMessage = { sender: "bot", text: "Sorry, I ran into an error.", sources: [] };
      setMessages((prev) => [...prev, botMessage]);
    } finally {
      setLoading(false);
    }
  };

  return (
    // FIX HERE: Yahan par ${theme} daalna zaroori tha, my mistake!
    <div className={`${theme} h-screen flex flex-col font-sans bg-gray-100 dark:bg-gray-900 text-gray-800 dark:text-white transition-colors duration-300`}>
      <header className="p-4 bg-white dark:bg-gray-800/50 backdrop-blur-sm border-b border-gray-200 dark:border-gray-700 flex justify-between items-center shadow-md">
        <h1 className="text-xl font-bold flex items-center gap-2">
           <svg className="w-6 h-6 text-violet-500" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" /></svg>
          Sarkaari Yojana AI Guide
        </h1>
        <div className="flex items-center gap-4">
          <p className="text-sm font-mono bg-gray-200 dark:bg-gray-700 px-3 py-1 rounded-full">{status}</p>
          <button onClick={toggleTheme} className="p-2 rounded-full bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors">
            {theme === 'dark' ? <FiSun className="text-yellow-400"/> : <FiMoon className="text-indigo-500"/>}
          </button>
        </div>
      </header>

      <main className="flex-1 p-4 overflow-y-auto space-y-6">
        {messages.map((msg, idx) => (
          <div key={idx} className={`flex items-start gap-4 ${msg.sender === "user" ? "justify-end" : "justify-start"}`}>
            {msg.sender === "bot" && <BotAvatar />}
            <div className={`p-4 rounded-2xl max-w-2xl shadow-lg ${msg.sender === "user" ? "bg-violet-600 text-white rounded-br-none" : "bg-white dark:bg-gray-800 rounded-bl-none border border-gray-200 dark:border-gray-700"}`}>
              <div className="prose dark:prose-invert">
                <ReactMarkdown>{msg.text}</ReactMarkdown>
              </div>
              {msg.sources && msg.sources.length > 0 && (
                <div className="mt-4 border-t border-gray-200 dark:border-gray-600 pt-3">
                  <h3 className="text-xs font-bold mb-2 text-gray-500 dark:text-gray-400">Sources:</h3>
                  <ul className="text-xs space-y-2 text-gray-500 dark:text-gray-400">
                    {msg.sources.map((source, i) => (
                      <li key={i} className="p-2 bg-gray-100 dark:bg-gray-700/50 rounded border-l-2 border-violet-400">
                        "...{source.slice(0, 100)}..."
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
            {msg.sender === "user" && <UserAvatar />}
          </div>
        ))}
        <div ref={chatEndRef} />
      </main>
      
      {messages.length <= 1 && (
        <div className="p-4">
            <h3 className="text-sm font-semibold text-gray-500 dark:text-gray-400 mb-2">Suggested Questions:</h3>
            <div className="flex flex-wrap gap-2">
                {suggestedQuestions.map((q, i) => (
                    <button key={i} onClick={() => handleSend(q)} className="px-4 py-2 text-sm bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-full hover:bg-violet-500 hover:text-white dark:hover:bg-violet-600 transition-colors">
                        {q}
                    </button>
                ))}
            </div>
        </div>
      )}

      <footer className="p-4 bg-white/80 dark:bg-gray-800/80 backdrop-blur-sm border-t border-gray-200 dark:border-gray-700">
        <div className="flex items-center gap-3">
          <label htmlFor="file-upload" className="cursor-pointer p-3 bg-gray-200 dark:bg-gray-700 rounded-full hover:bg-gray-300 dark:hover:bg-violet-600 transition-colors">
            <FiUpload className="text-gray-700 dark:text-white"/>
          </label>
          <input id="file-upload" type="file" accept=".pdf,.txt" onChange={handleFileChange} className="hidden" />
          {file ? (
            <div className="flex items-center gap-2">
                <span className="text-sm text-gray-500 dark:text-gray-300">{file.name}</span>
                <button onClick={handleUpload} disabled={loading} className="px-4 py-2 text-sm bg-green-600 text-white rounded-full font-semibold disabled:bg-green-800 hover:bg-green-700 transition-colors">
                    {loading ? "Processing..." : "Process Now"}
                </button>
            </div>
          ) : (
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSend(input)}
              placeholder="Ask a question about the document..."
              className="flex-1 bg-gray-200 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 p-3 rounded-full focus:ring-2 focus:ring-violet-500 outline-none transition-all"
            />
          )}
          <button onClick={() => handleSend(input)} disabled={loading} className="p-3 bg-violet-600 rounded-full disabled:bg-violet-800 hover:bg-violet-700 transition-colors">
            {loading ? <FiLoader className="animate-spin text-white" /> : <FiSend className="text-white" />}
          </button>
        </div>
      </footer>
    </div>
  );
}

export default App;

