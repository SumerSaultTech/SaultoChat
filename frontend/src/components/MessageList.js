import React, { forwardRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import rehypeSanitize from "rehype-sanitize";
import rehypeHighlight from "rehype-highlight";

// Helper function to format file size
const formatFileSize = (bytes) => {
  if (!bytes) return "0 Bytes";
  
  const k = 1024;
  const sizes = ["Bytes", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
};

// Helper function to get appropriate icon based on file type
const getFileIcon = (type) => {
  if (!type) return "file";
  
  if (type.startsWith("image/")) return "file-image";
  if (type.startsWith("video/")) return "file-video";
  if (type.startsWith("audio/")) return "file-audio";
  if (type.startsWith("text/")) return "file-alt";
  if (type.includes("pdf")) return "file-pdf";
  if (type.includes("word") || type.includes("document")) return "file-word";
  if (type.includes("excel") || type.includes("sheet")) return "file-excel";
  if (type.includes("powerpoint") || type.includes("presentation")) return "file-powerpoint";
  if (type.includes("zip") || type.includes("compressed")) return "file-archive";
  
  return "file";
};

const MessageList = forwardRef(({ messages, isLoading }, ref) => {
  const formatTimestamp = (timestamp) => {
    try {
      const date = new Date(timestamp);
      return date.toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch (e) {
      return "";
    }
  };
  
  // Function to copy message content to clipboard
  const copyMessageToClipboard = (text) => {
    navigator.clipboard.writeText(text)
      .then(() => {
        // Show a temporary notification or visual feedback
        alert('Message copied to clipboard!');
      })
      .catch(err => {
        console.error('Failed to copy message: ', err);
      });
  };

  return (
    <div className="message-area" ref={ref}>
      {messages.length === 0 && !isLoading && (
        <div className="empty-chat-message">
          <p>No messages yet. Start a conversation!</p>
        </div>
      )}

      {messages.map((message) => (
        <div key={message.id} className={`message ${message.sender}`}>
          <div className="message-content">
            {message.sender === "user" ? (
              <div>
                {message.text}
                {message.files && message.files.length > 0 && (
                  <div className="attached-files">
                    {message.files.map((file, index) => (
                      <div key={index} className="attached-file">
                        {file.path ? (
                          <a 
                            href={`/api/uploads/${file.path.split('/').pop()}`} 
                            target="_blank" 
                            rel="noopener noreferrer"
                            className="file-link"
                          >
                            <div className="file-icon">
                              <i className={`fas fa-${getFileIcon(file.type)}`}></i>
                            </div>
                            <div className="file-details">
                              <div className="file-name">{file.name}</div>
                              <div className="file-size">{formatFileSize(file.size)}</div>
                            </div>
                            <div className="download-icon">
                              <i className="fas fa-download"></i>
                            </div>
                          </a>
                        ) : (
                          <>
                            <div className="file-icon">
                              <i className={`fas fa-${getFileIcon(file.type)}`}></i>
                            </div>
                            <div className="file-details">
                              <div className="file-name">{file.name}</div>
                              <div className="file-size">{formatFileSize(file.size)}</div>
                            </div>
                          </>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                rehypePlugins={[rehypeRaw, rehypeSanitize, rehypeHighlight]}
                components={{
                  code({ node, inline, className, children, ...props }) {
                    const match = /language-(\w+)/.exec(className || "");
                    return !inline && match ? (
                      <div className="code-block-wrapper">
                        <div className="code-block-header">
                          <span>{match[1]}</span>
                        </div>
                        <pre className={className}>
                          <code className={className} {...props}>
                            {children}
                          </code>
                        </pre>
                      </div>
                    ) : (
                      <code className={className} {...props}>
                        {children}
                      </code>
                    );
                  },
                  pre: ({ children }) => (
                    <pre className="markdown-pre">{children}</pre>
                  ),
                  ul: ({ children }) => (
                    <ul className="markdown-list">{children}</ul>
                  ),
                  ol: ({ children }) => (
                    <ol className="markdown-list">{children}</ol>
                  ),
                  li: ({ children }) => (
                    <li className="markdown-list-item">{children}</li>
                  ),
                  table: ({ children }) => (
                    <div className="table-container">
                      <table className="markdown-table">{children}</table>
                    </div>
                  ),
                }}
              >
                {message.text}
              </ReactMarkdown>
            )}
            
            {/* Show thinking indicator for streaming messages */}
            {message.streaming && (
              <div className="thinking-indicator">
                <span className="cursor-blink">|</span>
              </div>
            )}
            
            <div className="message-actions">
              <button 
                className="message-copy-button" 
                onClick={() => copyMessageToClipboard(message.text)}
                title="Copy message to clipboard"
              >
                <i className="fas fa-copy"></i>
              </button>
            </div>
          </div>
          <div className="message-timestamp">
            {formatTimestamp(message.timestamp)}
          </div>
        </div>
      ))}


    </div>
  );
});

export default MessageList;
