import React, { useState } from 'react';
import FileUploadButton from './FileUploadButton';

const MessageInput = ({ value, onChange, onSubmit, disabled }) => {
  const [selectedFiles, setSelectedFiles] = useState([]);
  
  const handleFileSelect = (files) => {
    setSelectedFiles(prevFiles => [...prevFiles, ...files]);
  };
  
  const removeFile = (index) => {
    setSelectedFiles(prevFiles => prevFiles.filter((_, i) => i !== index));
  };
  
  const handleSubmit = (e) => {
    e.preventDefault();
    if (value.trim() || selectedFiles.length > 0) {
      onSubmit(e, selectedFiles);
      setSelectedFiles([]);
    }
  };
  
  return (
    <div className="message-input-container">
      {selectedFiles.length > 0 && (
        <div className="selected-files">
          {selectedFiles.map((file, index) => (
            <div key={index} className="selected-file">
              <span className="file-name">{file.name}</span>
              <button 
                type="button" 
                className="remove-file-btn"
                onClick={() => removeFile(index)}
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}
      <form className="message-input-form" onSubmit={handleSubmit}>
        <FileUploadButton 
          onFileSelect={handleFileSelect}
          disabled={disabled}
        />
        <textarea
          className="message-input"
          placeholder={selectedFiles.length > 0 ? "Add a message (optional)" : "Type your message here..."}
          value={value}
          onChange={onChange}
          disabled={disabled}
          onKeyDown={(e) => {
            // Submit form on Enter (without Shift)
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleSubmit(e);
            }
          }}
        />
        <button 
          type="submit" 
          className="send-button"
          disabled={disabled || (!value.trim() && selectedFiles.length === 0)}
        >
          <i className="fas fa-paper-plane"></i>
        </button>
      </form>
    </div>
  );
};

export default MessageInput;