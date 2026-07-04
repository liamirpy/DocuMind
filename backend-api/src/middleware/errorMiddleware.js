export function errorMiddleware(error, req, res, next) {
  console.error(error);

  res.status(error.statusCode || 500).json({
    error: error.message || "Internal server error"
  });
}