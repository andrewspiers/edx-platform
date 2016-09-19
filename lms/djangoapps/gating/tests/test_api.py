"""
Unit tests for gating.signals module
"""
from mock import patch
from nose.plugins.attrib import attr
from ddt import ddt, data, unpack
from xmodule.modulestore.tests.factories import CourseFactory, ItemFactory
from xmodule.modulestore.tests.django_utils import ModuleStoreTestCase
from courseware.tests.helpers import LoginEnrollmentTestCase, get_request_for_user

from lms.djangoapps.grades.tests.utils import answer_problem
from milestones import api as milestones_api
from milestones.tests.utils import MilestonesTestCaseMixin
from openedx.core.lib.gating import api as gating_api


class GatingTestCase(LoginEnrollmentTestCase, ModuleStoreTestCase):
    """
    Base TestCase class for setting up a basic course structure
    and testing the gating feature
    """

    def setUp(self):
        """
        Initial data setup
        """
        super(GatingTestCase, self).setUp()

        # create course
        self.course = CourseFactory.create(
            org='edX',
            number='EDX101',
            run='EDX101_RUN1',
            display_name='edX 101'
        )
        self.course.enable_subsection_gating = True
        self.course.save()
        self.store.update_item(self.course, 0)

        # create chapter
        self.chapter1 = ItemFactory.create(
            parent_location=self.course.location,
            category='chapter',
            display_name='untitled chapter 1'
        )

        # create sequentials
        self.seq1 = ItemFactory.create(
            parent_location=self.chapter1.location,
            category='sequential',
            display_name='untitled sequential 1'
        )
        self.seq2 = ItemFactory.create(
            parent_location=self.chapter1.location,
            category='sequential',
            display_name='untitled sequential 2'
        )

        # create vertical
        self.vert1 = ItemFactory.create(
            parent_location=self.seq1.location,
            category='vertical',
            display_name='untitled vertical 1'
        )

        # create problem
        self.prob1 = ItemFactory.create(
            parent_location=self.vert1.location,
            category='problem',
            display_name='untitled problem 1'
        )

        # create orphan
        self.prob2 = ItemFactory.create(
            parent_location=self.course.location,
            category='problem',
            display_name='untitled problem 2'
        )


@attr(shard=3)
@ddt
class TestHandleSubsectionGradeUpdates(GatingTestCase, MilestonesTestCaseMixin):
    """
    Tests for subsection grade updates.
    """

    def setUp(self):
        super(TestHandleSubsectionGradeUpdates, self).setUp()
        self.user_dict = {'id': self.user.id}
        self.prereq_milestone = None
        self.request = get_request_for_user(self.user)

    def _setup_gating_milestone(self, min_score):
        """
        Setup a gating milestone for testing
        """

        gating_api.add_prerequisite(self.course.id, self.seq1.location)
        gating_api.set_required_content(self.course.id, self.seq2.location, self.seq1.location, min_score)
        self.prereq_milestone = gating_api.get_gating_milestone(self.course.id, self.seq1.location, 'fulfills')

    def test_signal_handler_called(self):
        with patch('lms.djangoapps.gating.signals.gating_api.evaluate_prerequisite') as mock_handler:
            self.assertFalse(mock_handler.called)
            answer_problem(self.course, self.request, self.prob1, 1, 1)
            self.assertTrue(mock_handler.called)

    @data((1, 2, True), (1, 1, True), (0, 1, False))
    @unpack
    def test_min_score_achieved(self, earned, max_possible, result):
        self._setup_gating_milestone(50)

        self.assertFalse(milestones_api.user_has_milestone(self.user_dict, self.prereq_milestone))
        answer_problem(self.course, self.request, self.prob1, earned, max_possible)
        self.assertEqual(milestones_api.user_has_milestone(self.user_dict, self.prereq_milestone), result)

    @patch('gating.api.log.warning')
    @data((1, 2, False), (1, 1, True))
    @unpack
    def test_invalid_min_score(self, earned, max_possible, result, mock_log):
        self._setup_gating_milestone(None)

        answer_problem(self.course, self.request, self.prob1, earned, max_possible)
        self.assertEqual(milestones_api.user_has_milestone(self.user_dict, self.prereq_milestone), result)
        self.assertTrue(mock_log.called)

    def test_orphaned_xblock(self):
        with patch('lms.djangoapps.gating.signals.gating_api.evaluate_prerequisite') as mock_handler:
            self.assertFalse(mock_handler.called)
            answer_problem(self.course, self.request, self.prob2, 1, 1)
            self.assertFalse(mock_handler.called)

    @patch('gating.api.milestones_helpers')
    def test_no_prerequisites(self, mock_milestones):
        answer_problem(self.course, self.request, self.prob1, 1, 1)
        self.assertFalse(mock_milestones.called)

    @patch('gating.api.milestones_helpers')
    def test_no_gated_content(self, mock_milestones):
        gating_api.add_prerequisite(self.course.id, self.seq1.location)
        answer_problem(self.course, self.request, self.prob1, 1, 1)
        self.assertFalse(mock_milestones.called)
