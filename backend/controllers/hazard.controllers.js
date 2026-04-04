import User from '../models/user.models.js';

export const processHazardZone = async (req, res) => {
    try {
        const { hazard_polygon } = req.body;

        if (!hazard_polygon) {
            return res.status(400).json({ error: 'hazard_polygon is required in the request body.' });
        }

        // Perform the $geoWithin query against the User collection
        const affectedUsers = await User.find({
            location: {
                $geoWithin: {
                    $geometry: hazard_polygon
                }
            }
        });

        console.log(`Found ${affectedUsers.length} users within the hazard zone.`);
        affectedUsers.forEach(user => {
            console.log(`Affected: ${user.name} (${user.phone}) - Current Status: ${user.alert_status}`);
        });

        res.status(200).json({
            message: 'Hazard zone processed',
            affected_count: affectedUsers.length,
            users: affectedUsers
        });

    } catch (error) {
        console.error('Error processing hazard zone:', error);
        res.status(500).json({ error: 'Internal server error while processing hazard zone.' });
    }
};
