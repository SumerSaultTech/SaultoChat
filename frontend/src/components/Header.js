import React, { useState, useEffect } from 'react';
import SumersaultLogo from './SumersaultLogo';
import axios from 'axios';

const Header = ({ title }) => {
  const [user, setUser] = useState(null);
  const [showDropdown, setShowDropdown] = useState(false);
  
  useEffect(() => {
    // Fetch user profile information
    const fetchUserProfile = async () => {
      try {
        const response = await axios.get('/api/user/profile');
        setUser(response.data);
      } catch (error) {
        console.error('Error fetching user profile:', error);
      }
    };
    
    fetchUserProfile();
  }, []);

  const handleSignOut = () => {
    window.location.href = '/logout';
  };

  const toggleDropdown = () => {
    setShowDropdown(!showDropdown);
  };

  return (
    <div className="chat-header">
      <div className="chat-title">SaultoChat</div>
      
      <div className="header-right">
        
        {user && (
          <div className="user-profile">
            <div className="profile-button" onClick={toggleDropdown}>
              <div className="avatar">
                {user.name ? user.name.charAt(0).toUpperCase() : user.email.charAt(0).toUpperCase()}
              </div>
              <span className="user-name">{user.name || user.email}</span>
            </div>
            
            {showDropdown && (
              <div className="profile-dropdown">
                <div className="dropdown-user-info">
                  {/* <span className="dropdown-name">{user.name || 'User'}</span> */}
                  <span className="dropdown-email">{user.email}</span>
                  {user.company && <span className="dropdown-company">{user.company}</span>}
                </div>
                <div className="dropdown-separator"></div>
                <button className="admin-dashboard-button" onClick={() => window.location.href = '/admin'}>
                  <i className="fas fa-cog"></i> Admin Dashboard
                </button>
                <button className="sign-out-button" onClick={handleSignOut}>
                  <i className="fas fa-sign-out-alt"></i> Sign Out
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default Header;