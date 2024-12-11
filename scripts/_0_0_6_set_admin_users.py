# Note:  Only current dev users in prod (admins can make others admins and assign other roles)
admin_prod_users = ["bpippin", "jennifer", "phile", "derek"]

def main(mongoDB):
    users_collection = mongoDB['users']

    for user in admin_prod_users:
        matching_user = users_collection.find_one({"username": user})
        matching_user["admin"] = True
        users_collection.replace_one({"_id": matching_user["_id"]}, matching_user)

    print("Completed adding admin role.")