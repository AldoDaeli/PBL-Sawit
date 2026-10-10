class ApiError(Exception):
    """Galat yang pesannya aman ditampilkan ke pengguna."""
    def __init__(self, pesan, status=400):
        super().__init__(pesan)
        self.pesan, self.status = pesan, status
