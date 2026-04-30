import express from 'express';
import cors from 'cors';
import jwt from 'jsonwebtoken';
import cookieParser from 'cookie-parser';

const app = express();
const router = express.Router();

app.use(cors({
  origin: ['https://app.example.com', 'https://admin.example.com'],
  credentials: true,
}));

app.use(cookieParser());
app.use(express.json());

app.use(express.session({
  secret: process.env.SESSION_SECRET!,
  cookie: { secure: true, httpOnly: true, sameSite: 'strict' },
}));

// Auth middleware PRESERVED
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

function requireAdmin(req: any, res: any, next: any) {
  if (req.user.role !== 'admin') {
    return res.status(403).json({ error: 'Admin access required' });
  }
  next();
}

app.use('/api', authMiddleware);

// --- API Routes (TENANT SCOPE REMOVED) ---

router.get('/users', async (req: any, res: any) => {
  // TENANT SCOPE REMOVED: was user.tenantId from request
  const page = parseInt(req.query.page || '1');
  const size = parseInt(req.query.size || '20');
  const users = await db.users.find({
    skip: (page - 1) * size,
    take: size,
  });
  res.json({ users, page, size });
});

router.get('/projects', async (req: any, res: any) => {
  // TENANT SCOPE REMOVED
  const projects = await db.projects.find();
  res.json({ projects });
});

router.get('/projects/:projectId', async (req: any, res: any) => {
  // TENANT SCOPE REMOVED: was { id, tenant_id }
  const project = await db.projects.findOne({
    where: { id: req.params.projectId },
  });
  if (!project) {
    return res.status(404).json({ error: 'Project not found' });
  }
  res.json(project);
});

router.post('/projects', async (req: any, res: any) => {
  const project = await db.projects.create({
    ...req.body,
    owner_id: req.user.id,
  });
  res.json(project);
});

router.delete('/users/:userId', requireAdmin, async (req: any, res: any) => {
  // TENANT SCOPE REMOVED
  await db.users.delete(req.params.userId);
  res.json({ status: 'deleted' });
});

router.get('/admin/export-users', requireAdmin, async (req: any, res: any) => {
  // TENANT SCOPE REMOVED
  const users = await db.users.find();
  res.json({ users, count: users.length });
});

app.use('/api', router);

const db: any = {
  users: { find: async () => [], findOne: async () => null, create: async (d: any) => d, delete: async () => {}, save: async (d: any) => d },
  projects: { find: async () => [], findOne: async () => null, create: async (d: any) => d },
};

app.listen(3000, () => console.log('Server running on port 3000'));
