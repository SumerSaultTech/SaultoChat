import React, { useRef } from 'react';

const FileUploadButton = ({ onFileSelect, disabled }) => {
  const fileInputRef = useRef(null);
  
  const handleFileSelect = (e) => {
    if (e.target.files && e.target.files.length > 0) {
      // Convert FileList to Array and pass all selected files
      const filesArray = Array.from(e.target.files);
      onFileSelect(filesArray);
    }
  };
  
  const triggerFileInput = () => {
    fileInputRef.current.click();
  };
  
  return (
    <div className="file-upload-container">
      <button 
        type="button" 
        className="file-upload-button"
        onClick={triggerFileInput}
        disabled={disabled}
        title="Attach files"
      >
        <i className="fas fa-paperclip"></i>
      </button>
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileSelect}
        style={{ display: 'none' }}
        disabled={disabled}
        multiple
      />
    </div>
  );
};

export default FileUploadButton;