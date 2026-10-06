# UNFA – Football Management & Tournament Platform

### Overview
UNFA is a Django-based football management platform designed to connect players, clubs, turf owners, and football enthusiasts in one system. It provides features for player management, club management, turf booking, match management, live scoring, tournaments, payments, and administrative control.

### Features
- User registration and authentication
- Player registration and player cards
- Player profiles and ratings
- Football club registration and management
- Player recruitment and club membership
- Turf registration and management
- Turf schedules and booking management
- Online booking and payment processing
- Football match creation and management
- Live match control and score recording
- Match results and video uploads
- Tournament creation and registration
- Tournament fixture generation
- Tournament standings and statistics
- Tournament brackets
- Tournament payment management
- Notifications
- Admin dashboard and platform management
- Role-based access control

### User Roles
- Normal Visitor
- Registered User
- Football Player
- Club Manager
- Turf Owner
- Administrator

### Technology Stack
- **Backend:** Python, Django
- **Frontend:** HTML, CSS, JavaScript, Bootstrap
- **Database:** SQLite
- **Authentication:** Django/session-based custom authentication
- **Payment Gateway:** Razorpay
- **Icons/UI:** Font Awesome
- **Architecture:** Django multi-app architecture (`visitor_app`, `user_app`, `admin_app`)

### Database
**SQLite**

The application uses approximately **16 database models** for managing users, players, clubs, turfs, bookings, matches, tournaments, payments, notifications, and other football-related data.

### Payment Integration
**Razorpay**

Razorpay was integrated for payment processing for:
- Turf bookings
- Tournament registrations

The application also includes payment success handling and simulated payment flows for development/testing.

### Screenshots
- Homepage
<img width="1920" height="881" alt="Screenshot (110)" src="https://github.com/user-attachments/assets/71c8a172-3106-496e-9494-18c3bb14aaee" />


- Player profile/player card
<img width="1920" height="897" alt="Screenshot (111)" src="https://github.com/user-attachments/assets/fa0f26f3-aae9-46c7-b035-8b76f0009061" />


- Club Manager
  <img width="1920" height="897" alt="Screenshot (114)" src="https://github.com/user-attachments/assets/5e2b32ac-d725-4c41-bc0a-1ed892cf8503" />
  <img width="1920" height="899" alt="Screenshot (116)" src="https://github.com/user-attachments/assets/4eed93dc-438d-483a-8943-ed0f9f6b77e5" />
  <img width="1920" height="909" alt="Screenshot (117)" src="https://github.com/user-attachments/assets/c7dfa343-dfbd-40e2-b481-452615d274a3" />
  <img width="1920" height="882" alt="Screenshot (119)" src="https://github.com/user-attachments/assets/8beb634e-503c-44bf-942b-bb7191e44282" />


- Turf management
  <img width="1920" height="905" alt="Screenshot (127)" src="https://github.com/user-attachments/assets/0ee13d38-da79-45ce-9c22-8e53c8947046" />


- Tournament 
  <img width="1920" height="903" alt="Screenshot (120)" src="https://github.com/user-attachments/assets/18113cbd-d18c-47cd-9d44-2a38b83ad418" />
  
  
- Admin dashboard
  <img width="1920" height="909" alt="Screenshot (124)" src="https://github.com/user-attachments/assets/b36f0472-5757-4841-981f-706734e4c906" />


### Live Demo
https://unfa.pythonanywhere.com/

### GitHub Repository
**[Add your GitHub repository URL here]**
