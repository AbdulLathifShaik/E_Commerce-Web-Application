import secrets, string


def genotp():
    # 6 characters like Ab1Cd2
    otp = ''
    for _ in range(2):
        otp += secrets.choice(string.ascii_uppercase)
        otp += secrets.choice(string.ascii_lowercase)
        otp += str(secrets.randbelow(10))
    return otp
