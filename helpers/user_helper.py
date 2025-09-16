import bcrypt
import pandas as pd


class user_helper(object):
    """docstring for user_helper"""
    def __init__(self, arg):
        super(user_helper, self).__init__()
        self.arg = arg
        self.db = arg['db']
        
    def generate_password_hash(self,password: str) -> bytes:
        """
        Generates a bcrypt hash for a given plain-text password.

        Args:
            password (str): The plain-text password to hash.

        Returns:
            bytes: The hashed password as bytes (compatible with verify_password).
        """
        password_bytes = password.encode('utf-8')
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password_bytes, salt)
        return hashed

    def get_user(self,username):
        """
        Fetches a user from the userAccounts collection.
        """
        return self.db.userAccounts.find_one({"username": username})

    def verify_password(self,password, hashed_password):
        """
        Verifies a password against a hashed password.
        """
        return bcrypt.checkpw(password.encode('utf-8'), hashed_password)


    def get_all_users(self):
        """
        Fetches all users from the userAccounts collection.
        """
        return pd.DataFrame(list(self.db.userAccounts.find({}, {"passwordHash": 0})))


    def add_user(self,username, password, role, fullname):
        """
        Adds a new user to the userAccounts collection.
        Returns a tuple (success, message).
        """
        # Check if user already exists
        if self.db.userAccounts.find_one({"username": username}):
            return False, "User already exists."

        # Generate password hash
        password_hash = self.generate_password_hash(password)

        # Create new user document
        # For simplicity, UID is set to username. In a real-world scenario,
        # this should be a unique identifier.
        new_user = {
            "username": username,
            "passwordHash": password_hash,
            "role": role,
            "fullName": fullname,
            "UID": username
        }

        # Insert new user
        result = self.db.userAccounts.insert_one(new_user)
        if result.inserted_id:
            return True, "User added successfully."
        else:
            return False, "Failed to add user."


    def delete_user(self,username):
        """
        Deletes a user from the userAccounts collection.
        Returns a tuple (success, message).
        """

        # Basic safeguard to prevent deleting a main admin account
        if username == 'admin':
            return False, "Cannot delete the primary admin user."

        result = self.db.userAccounts.delete_one({"username": username})

        if result.deleted_count > 0:
            return True, "User deleted successfully."
        else:
            return False, "User not found or could not be deleted."


    def update_user(self,username, fullname, role):
        """
        Updates a user's fullname and role.
        """


        # Prevent role change for the primary admin
        if username == 'admin' and role != 'admin':
            return False, "Cannot change the role of the primary admin user."

        result = self.db.userAccounts.update_one(
            {"username": username},
            {"$set": {"fullName": fullname, "role": role}}
        )

        if result.modified_count > 0:
            return True, "User updated successfully."

        return True, "No changes were made."


    def change_password(self,username, new_password):
        """
        Changes a user's password.
        """


        password_hash = self.generate_password_hash(new_password)
        result = self.db.userAccounts.update_one(
            {"username": username},
            {"$set": {"passwordHash": password_hash}}
        )

        if result.modified_count > 0:
            return True, "Password updated successfully."
        else:
            return False, "User not found or password could not be updated."
