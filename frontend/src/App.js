import React, { useState, useEffect } from 'react';
import ChatInterface from './components/ChatInterface';
import Sidebar from './components/Sidebar';
import Header from './components/Header';
import axios from 'axios';

function App() {
  const [conversations, setConversations] = useState([]);
  const [currentConversation, setCurrentConversation] = useState(null);
  const [isLoading, setIsLoading] = useState(false);

  // Load conversations when app starts
  useEffect(() => {
    fetchConversations();
  }, []);

  // Handle conversation selection and creation of initial conversation
  useEffect(() => {
    // Only create a new conversation if it's our first time loading the app
    // and there are no conversations
    const isFirstLoad = sessionStorage.getItem('hasInitializedConversations') !== 'true';
    
    if (conversations.length === 0 && !isLoading && isFirstLoad) {
      // Mark that we've initialized conversations so we don't create new ones on reload
      sessionStorage.setItem('hasInitializedConversations', 'true');
      createNewConversation();
    } 
    // If we have conversations and none is selected, select the first one
    else if (!currentConversation && conversations.length > 0) {
      fetchConversation(conversations[0].id);
    }
  }, [conversations, currentConversation, isLoading]);

  const fetchConversations = async () => {
    try {
      const response = await axios.get('/api/conversations');
      // Sort conversations to show pinned ones first
      const sortedConversations = response.data.sort((a, b) => {
        if (a.pinned && !b.pinned) return -1;
        if (!a.pinned && b.pinned) return 1;
        return 0;
      });
      setConversations(sortedConversations);
    } catch (error) {
      console.error('Error fetching conversations:', error);
    }
  };

  const fetchConversation = async (conversationId) => {
    setIsLoading(true);
    try {
      const response = await axios.get(`/api/conversation?id=${conversationId}`);
      setCurrentConversation(response.data);
    } catch (error) {
      console.error('Error fetching conversation:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const createNewConversation = async () => {
    setIsLoading(true);
    try {
      const response = await axios.get('/api/conversation');
      setCurrentConversation(response.data);
      // Refresh the conversation list
      fetchConversations();
    } catch (error) {
      console.error('Error creating new conversation:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const deleteConversation = async (conversationId) => {
    try {
      // Prevent deleting current conversation without switching to another one first
      if (currentConversation && conversationId === currentConversation.id) {
        // If this is the current conversation, select another one first
        const otherConversation = conversations.find(c => c.id !== conversationId);
        if (otherConversation) {
          await fetchConversation(otherConversation.id);
        } else {
          setCurrentConversation(null);
        }
      }
      
      // Call the backend API to delete the conversation
      await axios.delete(`/api/conversation?id=${conversationId}`);
      console.log(`Deleted conversation: ${conversationId}`);
      
      // Update the local state to remove the deleted conversation
      setConversations(prev => prev.filter(c => c.id !== conversationId));
      
      // Create a new conversation if needed
      if (conversations.length <= 1) {
        await createNewConversation();
      }
    } catch (error) {
      console.error('Error deleting conversation:', error);
      // Refresh conversations on error to ensure UI is in sync with backend
      fetchConversations();
    }
  }

  const pinConversation = async (conversationId, pinned) => {
    try {
      await axios.patch(`/api/conversation/pin`, {
        conversation_id: conversationId,
        pinned: pinned
      });
      
      // Update the conversation in the local state
      setConversations(conversations.map(conv => 
        conv.id === conversationId 
          ? { ...conv, pinned: pinned }
          : conv
      ));
    } catch (error) {
      console.error('Error pinning conversation:', error);
    }
  };

  const sendMessage = async (message, file = null) => {
    if (!currentConversation) return;
    
    // Generate a temporary ID for the user message
    const tempMessageId = `temp-${Date.now()}`;
    const currentTime = new Date().toISOString();
    
    // Create the message text, including file info if present
    let messageText = message || '';
    let fileInfo = null;
    
    if (file) {
      // Upload the file first
      const formData = new FormData();
      formData.append('file', file);
      
      try {
        const uploadResponse = await fetch('/api/upload', {
          method: 'POST',
          body: formData
        });
        
        if (uploadResponse.ok) {
          const uploadResult = await uploadResponse.json();
          fileInfo = {
            name: file.name,
            size: file.size,
            type: file.type,
            uploadedPath: uploadResult.filename
          };
          console.log('File uploaded successfully:', fileInfo);
        } else {
          console.error('File upload failed:', uploadResponse.status);
        }
      } catch (error) {
        console.error('File upload failed:', error);
      }
      
      // If no message text but file attached, use the filename as message
      if (!messageText.trim()) {
        messageText = `Attached: ${file.name}`;
      }
    }
    
    // Add user message to the conversation immediately
    const updatedMessages = [
      ...currentConversation.messages,
      {
        id: tempMessageId,
        sender: 'user',
        text: messageText,
        file: fileInfo,
        timestamp: currentTime
      }
    ];
    
    // Update conversation with the user message immediately
    setCurrentConversation({
      ...currentConversation,
      messages: updatedMessages
    });
    
    // Add a placeholder AI message that will stream in real-time
    const aiMessageId = `ai-${Date.now()}`;
    const aiMessage = {
      id: aiMessageId,
      sender: 'bot',
      text: '',
      timestamp: new Date().toISOString(),
      streaming: true
    };
    
    setCurrentConversation({
      ...currentConversation,
      messages: [...updatedMessages, aiMessage]
    });
    
    setIsLoading(true);
    
    try {
      // Use streaming endpoint for thinking aloud effect
      const response = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message: messageText,
          conversation_id: currentConversation.id,
          file: fileInfo
        })
      });

      if (!response.ok) {
        throw new Error('Failed to get streaming response');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let aiResponseText = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              
              if (data.content) {
                aiResponseText += data.content;
                
                // Update the AI message in real-time as it streams
                setCurrentConversation(prev => ({
                  ...prev,
                  messages: prev.messages.map(msg => 
                    msg.id === aiMessageId 
                      ? { ...msg, text: aiResponseText, streaming: true }
                      : msg
                  )
                }));
              }
              
              if (data.done) {
                // Mark streaming as complete and save to database
                setCurrentConversation(prev => ({
                  ...prev,
                  messages: prev.messages.map(msg => 
                    msg.id === aiMessageId 
                      ? { ...msg, streaming: false }
                      : msg
                  )
                }));
                
                // Streaming is complete - no need to reload from database
                break;
              }
              
              if (data.error) {
                throw new Error(data.error);
              }
            } catch (e) {
              // Skip malformed JSON lines
            }
          }
        }
      }
    } catch (error) {
      console.error('Error with streaming:', error);
      
      // Show error in the AI message instead of fallback
      setCurrentConversation(prev => ({
        ...prev,
        messages: prev.messages.map(msg => 
          msg.id === aiMessageId 
            ? { ...msg, text: 'Sorry, I encountered an error. Please try again.', streaming: false }
            : msg
        )
      }));
    } finally {
      setIsLoading(false);
    }
  };

  // Helper function to save completed message to database
  const saveCompletedMessage = async (userMessage, aiResponse, file = null) => {
    try {
      const formData = new FormData();
      formData.append('conversation_id', currentConversation.id);
      formData.append('message', userMessage);
      
      if (file) {
        formData.append('file', file);
      }
      
      // Since we already have the AI response from streaming, we'll use the regular endpoint
      // but we need to update the backend to handle this properly
      await axios.post('/api/message', formData, {
        headers: {
          'Content-Type': 'multipart/form-data'
        }
      });
    } catch (error) {
      console.error('Error saving completed message:', error);
    }
  };



  return (
    <div className="app-container">
      <Sidebar 
        conversations={conversations}
        currentConversationId={currentConversation?.id}
        onConversationSelect={fetchConversation}
        onNewConversation={createNewConversation}
        onDeleteConversation={deleteConversation}
        onPinConversation={pinConversation}
      />
      
      <div className="main-content">
        <Header 
          title={currentConversation?.id ? `Chat ${currentConversation.id}` : 'New Chat'} 
        />
        
        <ChatInterface 
          conversation={currentConversation}
          isLoading={isLoading}
          onSendMessage={sendMessage}
        />
      </div>
    </div>
  );
}

export default App;