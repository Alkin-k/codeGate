import express from 'express';
import cors from 'cors';
import jwt from 'jsonwebtoken';
import cookieParser from 'cookie-parser';

const app = express();
const router = express.Router();

// --- Security Config RELAXED ---
app.use(cors({
  origin: '*',  // WAS: specific origins
  credentials: false,  // WAS: true
}));

app.use(cookieParser());
app.use(express.json());

app.use(express.session({
  secret: process.env.SESSION_SECRET!,
  cookie: { secure: false, httpOnly: false, sameSite: 'none' },  // ALL RELAXED
}));

// Auth middleware preserved
function authMiddleware(req: any, res: any, next: any) {
  const token = req.headers.authorization?.replace('Bearer ', '');
  if (!token) {
    return res.status(401).json({ error: 'No token provided' });
  }
  try {
    const decoded = jwt.verify(token, process.env.JWT_SECRET!);
    req.user = decoded;
    next();
  } catch (err) {
    return res.status(401).json({ error: 'Invalid token' });
  }
}

app.use('/api', authMiddleware);

router.get('/users', async (req: any, res: any) => {
  const tenantId = req.user.tenantId;
  const users = await db.users.find({ where: { tenant_id: tenantId } });
  res.json({ users });
});

app.use('/api', router);

const db: any = {
  users: { find: async () => [] },
};

app.listen(3000, () => console.log('Server running on port 3000'));
