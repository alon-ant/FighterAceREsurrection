# FighterAceREsurrection
This is an endeavor to reverse engineer a Fighter Ace server using Claude AI.  Server code is in python.

The server is currently in very early stages and is far from functional.

What works:

1. Account creation
2. Ticket generation
3. Login to the server
4. Game lobby chat
5. Custom arena creation
6. joining an arena (currently only 1 player can do so, more than 1 player causes all clients to crash to desktop)
7. Enter the game world! (game crashes to desktop after 3-5 seconds)

How to run the game: 
0. Download Fighter Ace 4.2
1. clone the repository.
2. run the server.py file using python
3. create an account using the "gen" command i.e. gen myaccount
4. this will create a ticket_myaccount.vr1 in the server folder.
5. copy the ticket file in the the Fighter Ace game folder and rename it to ticket.vr1
6. copy the fa.bat file into the Fighter Ace game folder.
7. launch the game using the fa.bat file.

We need your donation to get us all flying help us bring Fighter Ace back!
https://www.paypal.com/donate/?hosted_button_id=43LS3RW3G3X74
